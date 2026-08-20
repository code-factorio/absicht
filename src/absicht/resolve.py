"""Fold a store into a `Design`, and index the graph that comes out of it.

Two jobs, and they belong together because both are the seam between "the
store as files" and "the design as a graph": `load` walks a directory into
per-kind tuples, `resolve` folds them into the one record everything
downstream reads, and `Index` adds the lookups that `check`, `packet`,
`render`, `diff` and the query commands all need and none should rebuild.

Nothing here judges anything. A dangling ref is a fact this module reports
and `check` grades. The one refusal is a store with no design header: a
`Design` without an id, a title and a version is a design of nothing.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import get_args

from pydantic import ValidationError

from absicht.load import LoadedStore
from absicht.models.design import (
    Behavior,
    Design,
    Element,
    Observation,
    ObservationId,
    Outcome,
    Record,
    Ref,
    RelationshipType,
    Resource,
    State,
    Timing,
)

_REF_PATTERN: str = get_args(Ref)[1].pattern
_OBSERVATION_PATTERN: str = get_args(ObservationId)[1].pattern
_ANCHORED = frozenset({_REF_PATTERN, _OBSERVATION_PATTERN})
"""Read off the model itself, so a reader cannot drift from it.

An observation id is a reference too. It matches a different pattern, which is
why `Milestone.done_when` went unchecked until both patterns were listed here.
"""

COLLECTIONS: tuple[str, ...] = (
    "glossary",
    "actors",
    "goals",
    "requirements",
    "qualities",
    "constraints",
    "behaviors",
    "components",
    "interfaces",
    "data_entities",
    "resources",
    "libraries",
    "external_services",
    "assumptions",
    "decisions",
    "questions",
    "rejections",
    "milestones",
    "relationships",
    "notes",
)
"""The `Design` fields a store holds as files, in the model's own order.

Named rather than walked off the annotations, because `load` turns the same
list into directory names and a walk that also caught `exports` or
`revisions` would ask for directories that do not exist.
"""


class ResolveError(Exception):
    """The store parsed but cannot be folded into a `Design`.

    Distinct from a `LoadError` on purpose: "this file did not parse" is a
    fact about one file, "the store has no design.yaml" is a fact about the
    whole store, and only the second makes folding impossible.
    """


def resolve(loaded: LoadedStore) -> Design:
    """Assemble the loaded tuples into the `Design` artifact.

    `LoadedStore.errors` ride along in the input and are none of this
    function's business: `build` refuses a store with load errors rather than
    emitting a partial artifact, `check` reports them — `resolve` folds
    whatever parsed.

    The fold revalidates rather than copying fields across, because two of
    `Design`'s invariants — unique ids, contract-only exports — are only
    decidable once every file sits in one record.
    """
    if loaded.header is None:
        raise ResolveError(
            "the store has no usable design.yaml: a Design is built around its "
            "own id, title and version"
        )
    fields = loaded.header.model_dump() | {name: getattr(loaded, name) for name in COLLECTIONS}
    try:
        return Design.model_validate(fields)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '(root)'}: {error['msg']}"
            for error in exc.errors(include_url=False)
        )
        raise ResolveError(f"the store does not fold into one design: {problems}") from exc


# ------------------------------------------------------------------- the walk


def kind(ref: str) -> str:
    return ref.split(":", 1)[0]


def _carries_ref(annotation: object) -> bool:
    for meta in getattr(annotation, "__metadata__", ()):
        if getattr(meta, "pattern", None) in _ANCHORED:
            return True
    return any(_carries_ref(arg) for arg in get_args(annotation))


@cache
def ref_fields(record_type: type[Record]) -> tuple[str, ...]:
    """Which fields of a record hold refs, found from the model, not a table.

    A hand-written list would go stale on the first new field, and a field
    nobody walks is a trace nobody follows.
    """
    names = []
    for name, field in record_type.model_fields.items():
        if name == "id":  # an id defines, it does not reference
            continue
        if any(getattr(m, "pattern", None) in _ANCHORED for m in field.metadata) or _carries_ref(
            field.annotation
        ):
            names.append(name)
    return tuple(names)


def references(record: Record) -> Iterator[tuple[str, str]]:
    """Every `(field, ref)` a record names, whatever shape the field has."""
    for name in ref_fields(type(record)):
        value = getattr(record, name)
        if value is None:
            continue
        if isinstance(value, str):
            yield name, value
        else:
            yield from ((name, item) for item in value)


def carriers(element: Element) -> Iterator[Record]:
    """The element, plus the records nested inside it that hold refs."""
    yield element
    if isinstance(element, Behavior):
        yield from element.observations


@dataclass(frozen=True, slots=True)
class Reference:
    """One edge in the design: `source` points at `target` through `field`.

    `field` is why this is an object rather than a bare pair: `trace` labels
    its paths with the relation name, and `check`'s dangling-ref rule names
    the field a missing target was reached through. A `Relationship` lands
    here under its own type name, so one walk sees one kind of edge.
    """

    source: Ref
    field: str
    target: Ref


# ------------------------------------------------------------------ behaviors


def observed(behavior: Behavior) -> tuple[Ref, ...]:
    """What a behavior's observations point at, deduplicated and id-ordered.

    Composition targets ride along, because they are `at` refs; they are
    never followed. A composed behavior's touches stay its own.
    """
    return tuple(sorted({observation.at for observation in behavior.observations}))


def touches(behavior: Behavior, scope: frozenset[str]) -> bool:
    return any(observation.at in scope for observation in behavior.observations)


def composes(behavior: Behavior) -> tuple[Ref, ...]:
    """The behaviors this one is built from: an observation pointing at one."""
    return tuple(ref for ref in observed(behavior) if kind(ref) == "behavior")


class Scope(StrEnum):
    """A behavior's reach, computed from its observations.

    `local` — one component and nothing else; `system` — anything else,
    including nothing observed anywhere. Never a field: the author states
    observations and the classification follows, so a behavior that grows an
    observation on a second component becomes a system behavior with no edit
    to say so.
    """

    LOCAL = "local"
    SYSTEM = "system"


def scope_of(behavior: Behavior) -> Scope:
    """`local` iff the direct non-behavior touches are exactly one component."""
    outside = tuple(ref for ref in observed(behavior) if kind(ref) != "behavior")
    if len(outside) == 1 and kind(outside[0]) == "component":
        return Scope.LOCAL
    return Scope.SYSTEM


def effective_timing(observation: Observation, index: Index) -> Timing | None:
    """The timing that governs, resolved through whatever `at` names.

    `None` exactly for `must_not`, which carries no when at all. A dangling
    `at` resolves to no resource kind and so reads `immediate` — the same
    "resolves to nothing" policy the rest of this module holds.
    """
    if observation.outcome is Outcome.MUST_NOT:
        return None
    target = index.get(observation.at)
    resource_kind = target.resource_kind if isinstance(target, Resource) else None
    return observation.effective_timing(resource_kind)


# --------------------------------------------------------------------- index


class Index:
    """One lookup over a design and the designs it imports.

    Not a graph library — the graphs here are small and the need is narrow,
    so `trace` does its own traversal over exactly these mappings rather than
    this module growing one.
    """

    def __init__(self, design: Design, imports: Mapping[str, Design] | None = None) -> None:
        self.design = design
        self.imports = dict(imports or {})
        self.local: dict[str, Element] = {e.id: e for e in design.elements()}
        self.observations: dict[str, Observation] = {
            observation.id: observation
            for behavior in design.elements()
            if isinstance(behavior, Behavior)
            for observation in behavior.observations
        }
        self.foreign: dict[str, str] = {}
        self.public: set[str] = set()
        self.exported: dict[str, Element] = {}
        for design_id, other in self.imports.items():
            self.public.update(other.exports)
            for element in other.elements():
                self.foreign[element.id] = design_id
                if element.id in other.exports:
                    self.exported[element.id] = element

        self._out: dict[str, list[Reference]] = {}
        self._in: dict[str, list[Reference]] = {}
        for element in self.local.values():
            for carrier in carriers(element):
                for field, ref in references(carrier):
                    self._link(Reference(source=element.id, field=field, target=ref))
        for edge in design.relationships:
            self._link(
                Reference(source=edge.source_id, field=edge.type.value, target=edge.target_id)
            )

    def _link(self, edge: Reference) -> None:
        self._out.setdefault(edge.source, []).append(edge)
        # A target nothing defines is a dangling ref: it gets no incoming
        # entry, because nothing that exists was pointed at. The outgoing edge
        # stays, which is where `check`'s readers find it.
        if edge.target in self.local or edge.target in self.exported:
            self._in.setdefault(edge.target, []).append(edge)

    # ------------------------------------------------------------- resolution

    def get(self, ref: str) -> Element | None:
        return self.local.get(ref) or self.exported.get(ref)

    def resolves(self, ref: str) -> bool:
        return (
            ref in self.local
            or ref in self.public
            or ref in self.imports
            or ref in self.observations
        )

    def is_private_foreign(self, ref: str) -> bool:
        return ref in self.foreign and ref not in self.public

    def elements(self) -> Iterator[Element]:
        return iter(self.local.values())

    def of_type[T: Element](self, element_type: type[T]) -> Iterator[T]:
        return (e for e in self.local.values() if isinstance(e, element_type))

    # ------------------------------------------------------------------ edges

    def edges(self, edge_type: RelationshipType) -> Iterator[tuple[str, str]]:
        for edge in self.design.relationships:
            if edge.type is edge_type:
                yield edge.source_id, edge.target_id

    def targets_of(self, edge_type: RelationshipType) -> set[str]:
        return {target for _, target in self.edges(edge_type)}

    def sources_of(self, edge_type: RelationshipType) -> set[str]:
        return {source for source, _ in self.edges(edge_type)}

    def references_from(self, ref: str) -> tuple[Reference, ...]:
        """What `ref` points at, dangling targets included."""
        return tuple(self._out.get(ref, ()))

    def referenced_by(self, ref: str) -> tuple[Reference, ...]:
        """What points at `ref`. Only edges onto something that exists."""
        return tuple(self._in.get(ref, ()))

    # ------------------------------------------------------------------ graph

    def neighbours(self, ref: str) -> set[str]:
        """Both directions: what it names, and what names it.

        One direction would be arbitrary. An agent changing a component needs
        what the component calls and what calls the component, and neither is
        more its business than the other.
        """
        return {edge.target for edge in self._out.get(ref, ())} | {
            edge.source for edge in self._in.get(ref, ())
        }

    def ring(self, seed: frozenset[str], hops: int) -> set[str]:
        """Everything within `hops` steps of the seed, seed excluded."""
        seen = set(seed)
        frontier = set(seed)
        for _ in range(hops):
            nxt: set[str] = set()
            for ref in frontier:
                nxt |= self.neighbours(ref) - seen
            if not nxt:
                break
            seen |= nxt
            frontier = nxt
        return seen - set(seed)

    def orphaned(self, kind_prefix: str | None = None) -> tuple[Ref, ...]:
        """Ids nothing points at, in `Design` field order.

        `kind_prefix` is the `kind:` prefix of a ref. The CLI passes the
        `Kind` value from its own surface — a plain string here, because
        `absicht.cli` sits above this layer in the import stack and must not
        be imported from it.
        """
        prefix = f"{kind_prefix}:" if kind_prefix is not None else None
        return tuple(
            ref
            for ref in self.local
            if ref not in self._in and (prefix is None or ref.startswith(prefix))
        )


def subtree(index: Index, ref: Ref) -> frozenset[Ref]:
    """`ref` plus everything reachable from it by following refs outward.

    A dangling target resolves to nothing here either — it is `check`'s to
    report, and on a page it stays plain text rather than becoming a link to
    nowhere. Lives beside the `Index` it walks because three commands scope
    their output the same way, and one `--scope` flag should mean one thing
    wherever it appears.
    """
    seen = {ref}
    pending = [ref]
    while pending:
        for edge in index.references_from(pending.pop()):
            if index.get(edge.target) is not None and edge.target not in seen:
                seen.add(edge.target)
                pending.append(edge.target)
    return frozenset(seen)


def inherited_owners(index: Index) -> dict[Ref, str]:
    """Each unowned `unknown` mapped to the owner of the element referencing it.

    Exactly one referencing element must carry an owner — two referencing
    owners are an ambiguity, and ambiguity is not a guess — and the level is
    one: a referencing element's own `owner` field is read, never an owner it
    would itself inherit, so chains stop here. Computed, never stored.
    """
    owners: dict[Ref, str] = {}
    for ref, element in index.local.items():
        if element.state is not State.UNKNOWN or element.owner is not None:
            continue
        candidates = [
            owner
            for edge in index.referenced_by(ref)
            if (source := index.get(edge.source)) is not None and (owner := source.owner)
        ]
        if len(candidates) == 1:
            owners[ref] = candidates[0]
    return owners


def composed_by(index: Index, ref: Ref) -> tuple[Ref, ...]:
    """The behaviors whose observations assert that `ref` occurs.

    An `at` edge onto anything else is an observation, not composition, so a
    non-behavior answers empty — the prefix guard is the definition, not a
    filter bolted on.
    """
    if kind(ref) != "behavior":
        return ()
    return tuple(sorted({edge.source for edge in index.referenced_by(ref) if edge.field == "at"}))


def superseded_by(index: Index, ref: Ref) -> tuple[Ref, ...]:
    """The reverse of stored `supersedes`: who replaced `ref`.

    One hop per edge, never the transitive closure of a chain. Wrapped with
    the name rather than read as "referrers filtered by field", so the call
    sites say what they mean.
    """
    return tuple(
        sorted({edge.source for edge in index.referenced_by(ref) if edge.field == "supersedes"})
    )
