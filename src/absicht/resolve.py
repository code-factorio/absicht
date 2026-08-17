"""Fold a ``LoadedStore`` into the ``Design`` artifact and index its references.

`resolve` is the seam between "the store as files" and "the design as a
graph": `load` walks a directory into per-kind tuples, this module folds them
into the `Design` everything downstream reads, and `Index` adds the lookups
that `show`, `list`, `gaps` and `trace` all need and should not each rebuild —
an element by id, and each direction of its references ("what points at this
ref", "what this ref points at"), which `Element`'s own fields cannot answer
because references are one-directional by design.

This is deliberately not validation. A dangling ref simply never becomes a
key in the index (`check` turns it into a finding via `iter_references`), a
`contains` cycle resolves like any other edge, and the one refusal is a store
with no `System` element — a `Design` without one would be a design of
nothing. Deciding what a broken store means is `build`'s and `check`'s job,
one layer up.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from types import UnionType
from typing import get_args, get_origin, get_type_hints

from absicht.load import LoadedStore
from absicht.models import Behavior, Design, Element, Record, Ref, State, Story


class ResolveError(Exception):
    """The store parsed but cannot be folded into a `Design`.

    Distinct from a `LoadError` on purpose: "this file did not parse" is a
    fact about one file, "the store has no System element" is a fact about
    the whole store, and only the second makes folding impossible.
    """


def resolve(loaded: LoadedStore) -> Design:
    """Assemble the loaded tuples into the `Design` artifact.

    `LoadedStore.errors` ride along in the input and are none of this
    function's business: `build` refuses a store with load errors rather than
    emitting a partial artifact, `check` reports them — `resolve` folds
    whatever parsed.
    """
    if loaded.system is None:
        raise ResolveError(
            "the store has no usable system.yaml: a Design is built around its one System element"
        )
    return Design(
        system=loaded.system,
        externals=loaded.externals,
        requirements=loaded.requirements,
        non_functionals=loaded.non_functionals,
        stories=loaded.stories,
        components=loaded.components,
        seams=loaded.seams,
        data=loaded.data,
        resources=loaded.resources,
        behaviors=loaded.behaviors,
        decisions=loaded.decisions,
        rejections=loaded.rejections,
        questions=loaded.questions,
        milestones=loaded.milestones,
    )


@dataclass(frozen=True, slots=True)
class Reference:
    """One edge in the design: `source` points at `target` through `field`.

    `field` is why this is an object rather than a bare source ref: `trace`
    labels its paths with relation names, and `check`'s dangling-ref rule
    names the field a missing target was reached through.
    """

    source: Ref
    field: str
    target: Ref


def iter_references(design: Design) -> Iterator[Reference]:
    """Every reference edge in the design, in `Design` field order.

    Walking the annotations on `models.py`'s records rather than a hand-copied
    field list means a ref-typed field added to a model is indexed — and
    checked, and traceable — without this module learning about it. The spec's
    own field list already misses `Rejection.milestone` and
    `Milestone.unresolved`; the drift it warns about has precedent.
    """
    for element in _elements(design):
        yield from _references_of(element, source=element.id)
        if isinstance(element, Story):
            # A criterion is not an element: its id is a `CriterionId`, not a
            # `Ref`, so it gets no `by_id` entry of its own and its `touches`
            # are attributed to the story that carries it.
            for criterion in element.acceptance:
                yield from _references_of(criterion, source=element.id)
        if isinstance(element, Behavior):
            # An observation is the same shape of nested record: its `at` is
            # attributed to the behavior that carries it, which is what lets
            # the generic dangling-ref sweep and the index's reverse lookups
            # cover observation refs with no rule of their own.
            for observation in element.observations:
                yield from _references_of(observation, source=element.id)


def _elements(design: Design) -> tuple[Element, ...]:
    """Every addressable element, the system first and kinds in `Design` field
    order — the order `load` produced them in, so `by_id` and
    `iter_references` walk deterministically."""
    return (
        design.system,
        *design.externals,
        *design.requirements,
        *design.non_functionals,
        *design.stories,
        *design.components,
        *design.seams,
        *design.data,
        *design.resources,
        *design.behaviors,
        *design.decisions,
        *design.rejections,
        *design.questions,
        *design.milestones,
    )


def _references_of(record: Record, *, source: Ref) -> Iterator[Reference]:
    """The reference edges on one record's own ref-typed fields.

    Works for any `Record`, which is how a nested `Criterion` — a `Record`
    but not an `Element` — is walked under its story's id. `id` is skipped:
    it is identity, not a reference, and indexing it would make every element
    its own neighbour. `System.units` holds `Unit` records, not refs: units
    are not elements, nothing resolves them through `by_id`, and the
    multi-repo commands read `system.units` directly.
    """
    # `include_extras` is load-bearing: without it `get_type_hints` strips the
    # `Annotated` pattern off `Ref` and every field degrades to plain `str`,
    # which would make the walk see no references at all.
    for name, annotation in get_type_hints(type(record), include_extras=True).items():
        if name == "id" or not _holds_refs(annotation):
            continue
        value = getattr(record, name)
        targets = value if isinstance(value, tuple) else (value,) if value is not None else ()
        for target in targets:
            yield Reference(source=source, field=name, target=target)


def _holds_refs(annotation: object) -> bool:
    """True for `Ref`, `Ref | None` and `tuple[Ref, ...]` — the shapes a
    ref-typed field takes in `models.py`."""
    origin = get_origin(annotation)
    if origin is UnionType:
        members = [arg for arg in get_args(annotation) if arg is not type(None)]
        return len(members) == 1 and _holds_refs(members[0])
    if origin is tuple:
        args = get_args(annotation)
        return bool(args) and _holds_refs(args[0])
    return annotation is Ref


@dataclass(frozen=True, slots=True)
class Index:
    """The lookups over a resolved `Design` that several commands need and
    none should rebuild.

    Not a graph library — the project's graphs are small and the need is
    narrow, so `trace` does its own traversal over exactly these mappings
    rather than this module growing one.
    """

    by_id: dict[Ref, Element]
    referenced_by: dict[Ref, tuple[Reference, ...]]
    references_from: dict[Ref, tuple[Reference, ...]]
    """The mirror of `referenced_by`: what each element points at, which
    `show` walks for its outgoing side. It keeps edges `referenced_by` cannot
    hold — a source is always an element, so a dangling target still has its
    outgoing edge here, where `check`'s readers can find it."""

    @classmethod
    def from_design(cls, design: Design) -> Index:
        by_id = {element.id: element for element in _elements(design)}
        incoming: dict[Ref, list[Reference]] = {}
        outgoing: dict[Ref, list[Reference]] = {}
        for reference in iter_references(design):
            # A target that is not an element is a dangling ref: it gets no
            # entry, because nothing that exists was pointed at. The edge
            # stays in `iter_references` for `check` to report.
            if reference.target in by_id:
                incoming.setdefault(reference.target, []).append(reference)
            outgoing.setdefault(reference.source, []).append(reference)
        return cls(
            by_id=by_id,
            referenced_by={target: tuple(refs) for target, refs in incoming.items()},
            references_from={source: tuple(refs) for source, refs in outgoing.items()},
        )

    def orphaned(self, kind: str | None = None) -> tuple[Ref, ...]:
        """Ids with no entry in `referenced_by`, in `Design` field order.

        `kind` is the `kind:` prefix of a ref. The CLI passes the `Kind` value
        from its own surface — a plain string here, because `absicht.cli` sits
        above this layer in the import stack and must not be imported from it.
        The system element is included when no kind filters it out: it is the
        root of a design, being unpointed-at is its job, and the callers that
        care (`ab list --orphaned`, `ab gaps`) always name a kind.
        """
        prefix = f"{kind}:" if kind is not None else None
        return tuple(
            ref
            for ref in self.by_id
            if ref not in self.referenced_by and (prefix is None or ref.startswith(prefix))
        )


def subtree(index: Index, ref: Ref) -> frozenset[Ref]:
    """The subtree a ``--scope`` selects: ``ref`` plus everything reachable
    from it by following refs outward. Dangling targets resolve to nothing
    here either — they are ``ab check``'s to report, and on a page they stay
    plain text rather than becoming links to nowhere.

    Lives here, beside the ``Index`` it walks, because three commands scope
    their output the same way — the site and diagram halves of ``ab render``
    and ``ab diff`` — and one ``--scope`` flag should mean one thing wherever
    it appears.
    """
    seen = {ref}
    pending = [ref]
    while pending:
        for edge in index.references_from.get(pending.pop(), ()):
            if edge.target in index.by_id and edge.target not in seen:
                seen.add(edge.target)
                pending.append(edge.target)
    return frozenset(seen)


def inherited_owners(index: Index) -> dict[Ref, str]:
    """§7's owner inheritance, as a query over one index: each unowned
    ``unknown`` mapped to the owner of the element that references it.

    Exactly one referencing element must carry an owner — two referencing
    owners are an ambiguity, and ambiguity is not a guess — and the level is
    one: a referencing element's own ``owner`` field is read, never an owner
    it would itself inherit, so chains stop here. Computed, never stored
    (same inversion as ``parent`` with no ``children[]``).

    Lives here, beside the ``Index`` it reads, because two commands group
    unknowns by owner — ``ab gaps``' worklist and ``ab list --owner`` — and
    one inheritance rule should mean one thing wherever it appears.
    """
    owners: dict[Ref, str] = {}
    for ref, element in index.by_id.items():
        if element.state is not State.UNKNOWN or element.owner is not None:
            continue
        candidates = [
            owner
            for edge in index.referenced_by.get(ref, ())
            if (owner := index.by_id[edge.source].owner) is not None
        ]
        if len(candidates) == 1:
            owners[ref] = candidates[0]
    return owners
