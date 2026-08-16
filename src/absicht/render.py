"""Read-only projections of a resolved ``Design``, shared by every renderer.

Three things today, all living here for the same reason: the site generator
``docs/tasks/26-render-site.md`` builds on them and cannot import up the stack
— the element view behind ``ab show REF`` ("literally reuse 21-show.md's
function, don't re-derive it"), the gaps worklist behind ``ab gaps`` ("a gaps
page, reusing 23-gaps.md's worklist") and the trace paths behind ``ab trace
REF`` — plus the one mermaid emitter every ``--format mermaid`` output calls,
so two diagram spellings cannot drift apart (docs/tasks/27-render-diagrams.md).
The CLI stays a thin adapter over all of them; the projections and their
reasoning live here.

Rendering is deterministic because the data under it is: neighbours keep the
order ``Index`` indexed them in, which is ``models.py``'s field declaration
order, so the same store always spells the same view.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

from absicht.check import expired_externals
from absicht.models import SCHEMA_VERSION, Design, Element, Question, Ref, State
from absicht.resolve import Index, Reference


class UnknownRefError(Exception):
    """``REF`` names nothing in the store: a broken invocation, not a finding.

    ``ab show`` maps this to ``ExitCode.USAGE`` — the exit-code table's
    distinction between "the caller asked for something that is not there" and
    "the design has a problem".
    """


@dataclass(frozen=True, slots=True)
class Link:
    """One resolved edge of a neighbourhood: the element on the other side,
    and the field that carries the ref.

    The field belongs to the element nearer the focus — the focus itself for
    an outgoing hop, the pointing element for an incoming one — so a line like
    ``requirement:cancel-orders (realized_by)`` names both ends of the edge.
    """

    field: str
    other: Element


@dataclass(frozen=True, slots=True)
class Hop(Link):
    """An outgoing ``Link`` plus the hops it leads to, while depth remains."""

    deeper: tuple[Hop, ...] = ()


@dataclass(frozen=True, slots=True)
class Neighbourhood:
    """The answer to ``ab show``: one element with both sides of its graph."""

    element: Element
    outgoing: tuple[Hop, ...]
    incoming: tuple[Link, ...]

    def render_text(self, *, include_body: bool) -> str:
        lines = [f"{self.element.id} — {self.element.title}"]
        lines += [f"  {name}: {_value_text(value)}" for name, value in self._fields()]
        lines += _section(
            "points at:",
            (
                f"{'  ' * (level + 1)}{hop.other.id} ({hop.field})"
                for level, hop in _walk(self.outgoing)
            ),
        )
        lines += _section(
            "referenced by:", (f"  {link.other.id} ({link.field})" for link in self.incoming)
        )
        if include_body and self.element.body:
            lines += ["", self.element.body.rstrip()]
        return "\n".join(lines)

    def render_markdown(self, *, include_body: bool) -> str:
        """One Markdown document — the shape the site's element pages reuse."""
        lines = [f"# {self.element.title}", "", f"`{self.element.id}`"]
        lines += [f"- {name}: {_value_text(value)}" for name, value in self._fields()]
        lines += _section(
            "## Points at",
            (
                f"{'  ' * level}- `{hop.other.id}` — {hop.field}"
                for level, hop in _walk(self.outgoing)
            ),
        )
        lines += _section(
            "## Referenced by", (f"- `{link.other.id}` — {link.field}" for link in self.incoming)
        )
        if include_body and self.element.body:
            lines += ["", "## Body", "", self.element.body.rstrip()]
        return "\n".join(lines)

    def render_json(self, *, include_body: bool) -> dict[str, object]:
        """The ``--json``/``--format json`` envelope of ``00-conventions.md``."""
        exclude = None if include_body else {"body"}
        return {
            "schema_version": SCHEMA_VERSION,
            "element": self.element.model_dump(mode="json", exclude=exclude),
            "points_at": [_hop_json(hop) for hop in self.outgoing],
            "referenced_by": [
                {"field": link.field, "source": _fields_of(link.other)} for link in self.incoming
            ],
        }

    def _fields(self) -> tuple[tuple[str, Any], ...]:
        """The element's own fields for the prose renderers: declaration
        order, minus the header's four — `id` and `title` are the heading,
        `source` is provenance, `body` prints as its own block."""
        return tuple(
            (name, value)
            for name, value in self.element.model_dump(mode="json").items()
            if name not in ("id", "title", "source", "body") and value not in ("", None, [])
        )


def neighbourhood(design: Design, ref: str, *, depth: int) -> Neighbourhood:
    """Resolve ``ref`` into its neighbourhood, ``depth`` hops out.

    ``depth`` bounds the *outgoing* side only — "how far to follow refs" reads
    as following the element's own refs, while "what points at it" stays a
    neighbourhood view by stopping at one hop; expanding both directions would
    make ``show`` the pathfinder ``ab trace`` owns. ``depth 0`` therefore
    follows nothing out, leaving the element and whoever points at it. A ref
    whose target is not an element resolves to no neighbour on either side,
    the same policy ``Index.referenced_by`` already holds — reporting dangling
    refs is ``ab check``'s job, not a query's.
    """
    index = Index.from_design(design)
    element = index.by_id.get(ref)
    if element is None:
        raise UnknownRefError(f"unknown ref {ref!r}: no element in this store has that id")
    return Neighbourhood(
        element=element,
        # The first hop costs one unit of budget like every hop after it, so
        # the whole side is empty at depth 0 rather than quietly meaning 1.
        outgoing=(
            tuple(
                _hop(index, edge, remaining=depth - 1)
                for edge in index.references_from.get(ref, ())
                if edge.target in index.by_id
            )
            if depth > 0
            else ()
        ),
        incoming=tuple(
            Link(field=edge.field, other=index.by_id[edge.source])
            for edge in index.referenced_by.get(ref, ())
        ),
    )


def _hop(index: Index, edge: Reference, *, remaining: int) -> Hop:
    """One resolved outgoing edge, plus its own while budget remains.

    The budget is what makes cyclic graphs — a seam's provider provides that
    seam right back — safe: expansion stops when it runs out, not when the
    walk arrives somewhere it has already been. A view of a cyclic graph is a
    bounded tree, not a search.
    """
    deeper = (
        tuple(
            _hop(index, further, remaining=remaining - 1)
            for further in index.references_from.get(edge.target, ())
            if further.target in index.by_id
        )
        if remaining > 0
        else ()
    )
    return Hop(field=edge.field, other=index.by_id[edge.target], deeper=deeper)


def _walk(hops: tuple[Hop, ...], level: int = 0) -> Iterator[tuple[int, Hop]]:
    """Every hop with its distance from the focus, so the prose renderers
    indent by level without each re-implementing the recursion."""
    for hop in hops:
        yield level, hop
        yield from _walk(hop.deeper, level + 1)


def _section(heading: str, entries: Iterator[str]) -> list[str]:
    """A headed block, omitted whole when it has no entries — a view with
    nothing on one side says nothing about that side rather than proving an
    empty heading at the reader."""
    rows = list(entries)
    return ["", heading, *rows] if rows else []


def _value_text(value: Any) -> str:
    """One line per field value: strings as themselves, lists of strings
    comma-joined, anything structured (fields, criteria, units) as compact
    JSON rather than a bespoke pretty-printer per shape."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ", ".join(value)
    return json.dumps(value)


def _fields_of(element: Element) -> dict[str, object]:
    """A neighbour's fields: everything but its prose and provenance. The body
    is the focus element's to print (under ``--body``), and where a neighbour
    lives is not this view's story."""
    return element.model_dump(mode="json", exclude={"body", "source"})


def _hop_json(hop: Hop) -> dict[str, object]:
    return {
        "field": hop.field,
        "target": _fields_of(hop.other),
        "deeper": [_hop_json(deeper) for deeper in hop.deeper],
    }


# --- the gaps worklist --------------------------------------------------------

UNFINISHED_STATES = frozenset({State.UNKNOWN, State.OBSERVED, State.DELEGATED})
"""The states that put an element on the worklist: the ones the README calls
legitimate and expected rather than done. `specified`, `constrained` and
`out_of_scope` are not unfinished — the last is a decision, not a gap."""

# The reason vocabulary `ab gaps` spells on its worklist. Constants rather
# than literals at each use site: `ab gaps --overdue` and the text renderer
# match on these strings, and a drift there would fail silently — the filter
# would quietly answer nothing. The `state=<state>` reason is spelled where
# it is built; nothing keys on its value.
UNOWNED = "unowned"
QUESTION_OPEN = "question-open"
QUESTION_OVERDUE = "question-overdue"
EXTERNAL_EXPIRED = "external-expired"


@dataclass(frozen=True, slots=True)
class Gap:
    """One worklist entry: an element plus every reason it is unfinished.

    Distinct from a bare `Element` on purpose — the command's whole point is
    the *why*. `due_on` is carried only for question gaps (the one reason with
    a deadline) and `expires_on` only for expired externals (the one reason
    about a lapsed date), so a consumer can prioritize without re-reading the
    element; both stay `None` elsewhere rather than copying a date over.
    """

    element: Element
    reasons: tuple[str, ...]
    due_on: date | None = None
    expires_on: date | None = None


def worklist(design: Design, *, today: date) -> tuple[Gap, ...]:
    """Everything unfinished in one worklist, one entry per element, in id order.

    Four sources, unioned: an unfinished state, an unresolved `Question` (the
    whole kind is a gap by construction — "an `unknown` with an owner and a
    way out", and one a decision has `resolved_by` is closed), no owner, and
    an expired external assumption (`absicht.check`'s one spelling of
    "expired", reused). An element can arrive through several sources at once;
    the entry then carries every reason, in the order the sources are listed
    here — deterministic, like the id order the entries come in.

    "Unowned" is scoped to the unfinished states, deliberately narrower than
    "any element without an owner": a store that simply sets no owners (the
    fixtures never do) would land on the worklist whole and drown it, and the
    spec's own `clean/` expectation — empty, meant to be complete — pins the
    same reading. Who owns a finished element is `ab list --owner`'s question.
    """
    expired_on = {
        external.id: external.expires_on for external in expired_externals(design, today=today)
    }
    gaps: list[Gap] = []
    for element in sorted(Index.from_design(design).by_id.values(), key=lambda e: e.id):
        reasons: list[str] = []
        unfinished = element.state in UNFINISHED_STATES
        if unfinished:
            reasons.append(f"state={element.state.value}")
            if element.owner is None:
                reasons.append(UNOWNED)
        due_on: date | None = None
        if isinstance(element, Question) and element.resolved_by is None:
            overdue = element.due_on is not None and element.due_on < today
            reasons.append(QUESTION_OVERDUE if overdue else QUESTION_OPEN)
            due_on = element.due_on
        if element.id in expired_on:
            reasons.append(EXTERNAL_EXPIRED)
        if reasons:
            gaps.append(
                Gap(
                    element=element,
                    reasons=tuple(reasons),
                    due_on=due_on,
                    expires_on=expired_on.get(element.id),
                )
            )
    return tuple(gaps)


# --- the mermaid emitter ---------------------------------------------------------


def mermaid(nodes: Iterable[Ref], edges: Iterable[tuple[Ref, str, Ref]]) -> str:
    """One ``graph TD`` diagram from refs and labelled, directed edges.

    The one mermaid emitter in the project: ``ab trace --format mermaid``
    calls it with the subgraph its paths cover, and ``ab render --format
    mermaid`` (docs/tasks/27-render-diagrams.md) with its own node set, so
    the two outputs cannot drift apart. Mermaid node ids may not carry the
    ``:`` a ref is spelled with, so separators flatten to underscores and the
    full ref rides along as the label. Both iterables are rendered in the
    order given — determinism is the caller's duty, and both callers walk the
    design deterministically.
    """
    return "\n".join(
        [
            "graph TD",
            *(f'  {_node_id(ref)}["{ref}"]' for ref in nodes),
            *(
                f"  {_node_id(source)} -->|{field}| {_node_id(target)}"
                for source, field, target in edges
            ),
        ]
    )


def _node_id(ref: Ref) -> str:
    """The mermaid-safe spelling of a ref: unique per ref and stable, so the
    same design always spells the same ids. Colons would end the id, dashes
    read as mermaid syntax in some positions, so both flatten."""
    return ref.replace(":", "_").replace("-", "_")


# --- the trace paths -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Step:
    """One hop of a traced path: the ref-typed field that carries the edge,
    which way round it was followed, and the ref it arrives at.

    ``up`` spells the direction against the ref's own arrow — the element
    arrived at is the one whose field points back at where the walk came
    from — because "up" and "down" are the words ``ab trace``'s flags use.
    """

    field: str
    up: bool
    ref: Ref


@dataclass(frozen=True, slots=True)
class Trace:
    """The answer to ``ab trace``: every simple path out of (or between) refs.

    Paths never repeat a ref, and that invariant is the whole cycle guard: a
    cyclic graph answers a bounded set of paths instead of hanging.
    ``cycle_hit`` says the guard fired — a hop onto a ref already on the
    current path was declined. It is information about the shape of the graph
    (the schema invites reciprocal pairs like ``provides``/``provider``), not
    a finding; which relations may loop at all is ``ab check``'s
    ``integrity/cycle`` rule's judgement.
    """

    start: Ref
    target: Ref | None
    paths: tuple[tuple[Step, ...], ...]
    cycle_hit: bool

    def render_text(self) -> str:
        """One path per line, hops read left to right along the path:
        ``-->`` for a ref the left element carries, ``<--`` for a hop against
        one the right element carries."""
        lines = [self._line(path) for path in self.paths]
        if self.cycle_hit:
            lines.append(
                "note: a cycle was hit; paths stop at the first repeat rather than looping"
            )
        return "\n".join(lines)

    def render_json(self) -> dict[str, object]:
        """The ``--json``/``--format json`` envelope of ``00-conventions.md``:
        each path a sequence of steps, every step naming its relation,
        direction and arrival — plus the cycle flag, so a consumer knows the
        walk was bounded."""
        return {
            "schema_version": SCHEMA_VERSION,
            "from": self.start,
            "to": self.target,
            "paths": [
                [
                    {
                        "field": step.field,
                        "direction": "up" if step.up else "down",
                        "ref": step.ref,
                    }
                    for step in path
                ]
                for path in self.paths
            ],
            "cycle_hit": self.cycle_hit,
        }

    def render_mermaid(self) -> str:
        """The paths as one diagram: every element they cover as a node, every
        hop as an edge labelled with its relation and pointing the way the
        walk went. Auto-layout is mermaid's job — positions are `ab layout`'s
        (docs/tasks/24-trace.md keeps them out of scope here).
        """
        edges: list[tuple[Ref, str, Ref]] = []
        for path in self.paths:
            at = self.start
            for step in path:
                edges.append((at, step.field, step.ref))
                at = step.ref
        nodes = dict.fromkeys([self.start, *(step.ref for path in self.paths for step in path)])
        return mermaid(nodes, dict.fromkeys(edges))

    def _line(self, path: tuple[Step, ...]) -> str:
        line = self.start
        for step in path:
            arrow = f" <--{step.field}-- " if step.up else f" --{step.field}--> "
            line += arrow + step.ref
        return line


def trace_paths(
    design: Design, ref: str, *, to: str | None = None, up: bool = False, down: bool = False
) -> Trace:
    """Every simple path from ``ref`` outward and inward — or, with ``to``,
    between ``ref`` and ``to`` — in deterministic walk order.

    Direction: ``down`` follows refs the elements themselves carry, ``up``
    follows refs pointing back at the walk's current element, and neither
    flag (or both — redundant, not contradictory) walks either way. Without
    ``to`` every prefix is itself an answer: "the requirement and the
    component realizing it" is a traceability path, not noise around the
    longer ones.

    With ``to`` the walk is point-to-point, not the reachable set filtered:
    a backward pass first marks every element that can still reach the
    target under the same direction filter, and the walk only descends into
    marked ones, so wide dead ends cost nothing.

    Raises ``UnknownRefError`` for a ``ref`` or ``to`` no element has: a
    broken invocation, not an empty answer — ``ab trace`` maps it to
    ``USAGE``, like ``ab show``.
    """
    index = Index.from_design(design)
    if ref not in index.by_id:
        raise UnknownRefError(f"unknown ref {ref!r}: no element in this store has that id")
    if to is not None and to not in index.by_id:
        raise UnknownRefError(f"unknown --to ref {to!r}: no element in this store has that id")
    downs, ups = down or not up, up or not down

    def steps(node: Ref) -> tuple[Step, ...]:
        """A node's hops under the direction filter: its own refs outward
        first, then whoever points at it — each side in the order `Index`
        holds, which is what makes the walk deterministic."""
        hops: list[Step] = []
        if downs:
            hops += [
                Step(field=edge.field, up=False, ref=edge.target)
                # A dangling target resolves to no hop, the policy
                # `Index.referenced_by` already holds — reporting it is
                # `ab check`'s job, not a query's.
                for edge in index.references_from.get(node, ())
                if edge.target in index.by_id
            ]
        if ups:
            hops += [
                Step(field=edge.field, up=True, ref=edge.source)
                for edge in index.referenced_by.get(node, ())
            ]
        return tuple(hops)

    reaches = _reaches_target(index, to, steps) if to is not None else None
    paths: list[tuple[Step, ...]] = []
    visited = {ref}
    cycle_hit = False

    def walk(node: Ref, path: tuple[Step, ...]) -> None:
        nonlocal cycle_hit
        for step in steps(node):
            if reaches is not None and step.ref not in reaches:
                continue  # no route to the target from here; not a decline
            if step.ref in visited:
                # The cycle guard: following this hop would revisit an element
                # already on the path. Saying so is the point of `cycle_hit`.
                cycle_hit = True
                continue
            extended = (*path, step)
            if to is None:
                paths.append(extended)
            elif step.ref == to:
                paths.append(extended)
                continue  # a path ends at the target; nothing lies beyond it
            visited.add(step.ref)
            walk(step.ref, extended)
            visited.remove(step.ref)

    walk(ref, ())
    return Trace(start=ref, target=to, paths=tuple(paths), cycle_hit=cycle_hit)


def _reaches_target(
    index: Index, target: Ref, steps: Callable[[Ref], tuple[Step, ...]]
) -> frozenset[Ref]:
    """Every element with a route to ``target`` under ``steps`` — the prune
    set for the point-to-point walk, computed backwards from the target so
    the forward walk never enters a subtree it would have to abandon."""
    reverse: dict[Ref, list[Ref]] = {}
    for node in index.by_id:
        for step in steps(node):
            reverse.setdefault(step.ref, []).append(node)
    reaches = {target}
    queue = [target]
    while queue:
        for node in reverse.get(queue.pop(), ()):
            if node not in reaches:
                reaches.add(node)
                queue.append(node)
    return frozenset(reaches)
