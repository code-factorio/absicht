"""Read-only projections of a resolved ``Design``, shared by every renderer.

All living here for the same reason: everything downstream cannot import up
the stack. The element view behind ``ab show REF`` ("literally reuse
21-show.md's function, don't re-derive it"), the gaps worklist behind ``ab
gaps`` ("a gaps page, reusing 23-gaps.md's worklist") and the trace paths
behind ``ab trace REF``; the static site those three become under ``ab
render`` (docs/tasks/26-render-site.md) and the preview server that serves
it; plus the one mermaid emitter every ``--format mermaid`` output calls, so
two diagram spellings cannot drift apart (docs/tasks/27-render-diagrams.md),
and the Markdown document ``ab packet --format md`` writes
(docs/tasks/32-packet-cli.md). The CLI stays a thin adapter over all of them;
the projections and their reasoning live here.

Rendering is deterministic because the data under it is: neighbours keep the
order ``Index`` indexed them in, which is ``models.py``'s field declaration
order, so the same store always spells the same view. The one input that is
not design data — the clock the worklist's dated reasons hang on — is
injected by the caller, never read here.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from absicht.check import expired_externals
from absicht.models import (
    SCHEMA_VERSION,
    Behavior,
    Criterion,
    Design,
    Element,
    Fidelity,
    Observation,
    Outcome,
    Packet,
    PacketElement,
    Question,
    Ref,
    Resource,
    State,
    Timing,
)
from absicht.resolve import Index, Reference, inherited_owners, subtree

log = logging.getLogger(__name__)


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
class ObservationView:
    """One behavior observation with the timing that governs it.

    The effective timing is computed — §1.2's table over what ``at``
    resolved to, an authored value winning — never read from the authored
    field alone, because packet and verify need the same answer and none of
    them should re-derive the table. It is ``None`` exactly for ``must_not``,
    which carries no timing at all: "at no point" has no when.
    """

    observation: Observation
    effective_timing: Timing | None


@dataclass(frozen=True, slots=True)
class Neighbourhood:
    """The answer to ``ab show``: one element with both sides of its graph."""

    element: Element
    outgoing: tuple[Hop, ...]
    incoming: tuple[Link, ...]
    observations: tuple[ObservationView, ...] = ()
    """A behavior's observations with their effective timings; empty for
    every other kind, which is what keeps the field one concern."""

    def render_text(self, *, include_body: bool) -> str:
        lines = [f"{self.element.id} — {self.element.title}"]
        lines += [f"  {name}: {_value_text(value)}" for name, value in self._fields()]
        lines += _section(
            "observations:", (f"  {_observation_line(view)}" for view in self.observations)
        )
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
            "## Observations",
            (
                f"- `{view.observation.id}` — {view.observation.statement}"
                f" ({_observation_qualifiers(view)})"
                for view in self.observations
            ),
        )
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
        """The ``--json``/``--format json`` envelope of ``00-conventions.md``.

        The effective timing rides *beside* the authored one, additively per
        the envelope rules: ``timing`` stays exactly what the file said (null
        when unsaid), ``effective_timing`` is the derived answer a consumer
        acts on.
        """
        exclude = None if include_body else {"body"}
        dump = self.element.model_dump(mode="json", exclude=exclude)
        entries = cast("list[dict[str, object]]", dump.get("observations", []))
        for entry, view in zip(entries, self.observations, strict=True):
            entry["effective_timing"] = (
                view.effective_timing.value if view.effective_timing is not None else None
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "element": dump,
            "points_at": [_hop_json(hop) for hop in self.outgoing],
            "referenced_by": [
                {"field": link.field, "source": _fields_of(link.other)} for link in self.incoming
            ],
        }

    def _fields(self) -> tuple[tuple[str, Any], ...]:
        """The element's own fields for the prose renderers: declaration
        order, minus the header's four — `id` and `title` are the heading,
        `source` is provenance, `body` prints as its own block — and
        `observations`, which render as their own section: the one field a
        compact one-line value would bury five statements inside."""
        return tuple(
            (name, value)
            for name, value in self.element.model_dump(mode="json").items()
            if name not in ("id", "title", "source", "body", "observations")
            and value not in ("", None, [])
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
    return _neighbourhood(Index.from_design(design), ref, depth=depth)


def _neighbourhood(index: Index, ref: str, *, depth: int) -> Neighbourhood:
    """The neighbourhood over an index the caller already holds — the site's
    page-per-element loop passes one rather than re-deriving it per page."""
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
        observations=_observation_views(element, index),
    )


def _observation_views(element: Element, index: Index) -> tuple[ObservationView, ...]:
    """A behavior's observations with the timing that governs each — what
    `at` resolved to decides the default when the author said nothing, the
    same §1.2 table `Observation.effective_timing` spells. A dangling `at`
    resolves to no resource kind and so defaults `immediate`, the same
    "resolves to no neighbour" policy the outgoing side holds."""
    if not isinstance(element, Behavior):
        return ()
    views: list[ObservationView] = []
    for observation in element.observations:
        target = index.by_id.get(observation.at)
        resource_kind = target.resource_kind if isinstance(target, Resource) else None
        effective = (
            None
            if observation.outcome is Outcome.MUST_NOT
            else observation.effective_timing(resource_kind)
        )
        views.append(ObservationView(observation, effective))
    return tuple(views)


def _observation_qualifiers(view: ObservationView) -> str:
    """The stretch every observation rendering shares: outcome, effective
    timing (never for `must_not`), what it points at — the order a reader
    triages in. One spelling, so the text, markdown and site renderings of
    the view cannot drift apart."""
    qualifiers = [view.observation.outcome.value]
    if view.effective_timing is not None:
        qualifiers.append(view.effective_timing.value)
    qualifiers.append(f"at {view.observation.at}")
    return ", ".join(qualifiers)


def _observation_line(view: ObservationView) -> str:
    """One observation as the text format's line: the qualifiers, then the
    statement it makes."""
    return f"{view.observation.id}  {_observation_qualifiers(view)} — {view.observation.statement}"


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
NO_OBSERVATIONS = "no-observations"


@dataclass(frozen=True, slots=True)
class Gap:
    """One worklist entry: an element plus every reason it is unfinished.

    Distinct from a bare `Element` on purpose — the command's whole point is
    the *why*. `due_on` is carried only for question gaps (the one reason with
    a deadline) and `expires_on` only for expired externals (the one reason
    about a lapsed date), so a consumer can prioritize without re-reading the
    element; both stay `None` elsewhere rather than copying a date over.
    `owner_inherited` carries §7's inheritance — the owner of the single
    element referencing this unowned `unknown`, derived here and never
    stored, which is also why such an entry stops carrying `unowned`.
    """

    element: Element
    reasons: tuple[str, ...]
    due_on: date | None = None
    expires_on: date | None = None
    owner_inherited: str | None = None


def worklist(design: Design, *, today: date) -> tuple[Gap, ...]:
    """Everything unfinished in one worklist, one entry per element, in id order.

    Five sources, unioned: an unfinished state, no owner, a behavior with no
    observations (the query-side twin of `policy/behavior-needs-observations`,
    the way unowned elements appear both places — whatever the behavior's
    state, an expectation with nothing observable is not one), an unresolved
    `Question` (the whole kind is a gap by construction — "an `unknown` with
    an owner and a way out", and one a decision has `resolved_by` is closed),
    and an expired external assumption (`absicht.check`'s one spelling of
    "expired", reused). An element can arrive through several sources at once;
    the entry then carries every reason, in the order the sources are listed
    here — deterministic, like the id order the entries come in.

    "Unowned" is scoped to the unfinished states, deliberately narrower than
    "any element without an owner": a store that simply sets no owners (the
    fixtures never do) would land on the worklist whole and drown it, and the
    spec's own `clean/` expectation — empty, meant to be complete — pins the
    same reading. Who owns a finished element is `ab list --owner`'s question.
    Within it, §7's inheritance applies: an unowned `unknown` that inherits
    the owner of the single element referencing it (`inherited_owners`) is
    accounted for — annotated on the entry, not called unowned.
    """
    index = Index.from_design(design)
    inherited = inherited_owners(index)
    expired_on = {
        external.id: external.expires_on for external in expired_externals(design, today=today)
    }
    gaps: list[Gap] = []
    for element in sorted(index.by_id.values(), key=lambda e: e.id):
        reasons: list[str] = []
        unfinished = element.state in UNFINISHED_STATES
        if unfinished:
            reasons.append(f"state={element.state.value}")
            if element.owner is None and element.id not in inherited:
                reasons.append(UNOWNED)
        if isinstance(element, Behavior) and not element.observations:
            reasons.append(NO_OBSERVATIONS)
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
                    owner_inherited=inherited.get(element.id),
                )
            )
    return tuple(gaps)


def reasons_text(gap: Gap) -> str:
    """Every reason on one stretch of a worklist line, the dated ones with
    their date — the fact a reader triages on. One spelling, shared by the
    ``ab gaps`` text format and the site's gaps page, so the two cannot drift
    apart."""
    parts: list[str] = []
    for reason in gap.reasons:
        if reason in (QUESTION_OPEN, QUESTION_OVERDUE) and gap.due_on is not None:
            parts.append(f"{reason} (due {gap.due_on.isoformat()})")
        elif reason == EXTERNAL_EXPIRED and gap.expires_on is not None:
            parts.append(f"{reason} (expired {gap.expires_on.isoformat()})")
        else:
            parts.append(reason)
    return ", ".join(parts)


def owner_text(gap: Gap) -> str:
    """The §7 inheritance annotation, empty when the gap does not carry one —
    so the text line and the site's gaps page grow nothing in the common
    case. One spelling for both, so the marked form cannot drift apart."""
    return f"owner: {gap.owner_inherited} (inherited)" if gap.owner_inherited is not None else ""


def _attribution(gap: Gap) -> str:
    """A gap's annotation stretch: its reasons, then the inherited owner when
    there is one — the order the worklist line reads in."""
    return " — ".join(part for part in (reasons_text(gap), owner_text(gap)) if part)


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
            *(f'  {node_key(ref)}["{ref}"]' for ref in nodes),
            *(
                f"  {node_key(source)} -->|{field}| {node_key(target)}"
                for source, field, target in edges
            ),
        ]
    )


def node_key(ref: Ref) -> str:
    """The mermaid-safe spelling of a ref: unique per ref and stable, so the
    same design always spells the same ids. Colons would end the id, dashes
    read as mermaid syntax in some positions, so both flatten.

    Public because ``absicht.diagram``'s class statements must reference the
    node ids this spelling minted — a private twin would be free to drift.
    """
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


# --- the packet document -------------------------------------------------------------


def packet_markdown(packet: Packet, *, features_dir: str | None = None) -> str:
    """The ``--format md`` spelling of a ``Packet``: the brief an agent reads
    end to end (docs/tasks/32-packet-cli.md).

    Scope at full detail and the contract ring summarized to one line each —
    the ring is context to respect, not something to implement. The obligation
    sections print ``(none)`` rather than disappearing: "nothing constrains
    you" and "no rejection forbids anything" are facts an agent acts on, and a
    missing heading would read as a rendering gap instead.

    ``features_dir`` names where the ``.feature`` files landed when they were
    rendered, as the caller spelled it — relative, so the document stays
    byte-identical wherever the packet is written; the criteria section points
    there for the full Gherkin.
    """
    # `assemble` always carries the milestone itself at full fidelity; the
    # document's header covers it, so Scope is every other full element.
    milestone = next(element for element in packet.elements if element.ref == packet.milestone)
    identity = f"`{packet.milestone}`" + (f" — {packet.outcome}" if packet.outcome else "")
    scope = [
        element
        for element in packet.elements
        if element.fidelity is Fidelity.FULL and element.ref != packet.milestone
    ]
    ring = [element for element in packet.elements if element.fidelity is Fidelity.CONTRACT]
    criteria = [_criterion_text(criterion) for criterion in packet.criteria]
    if features_dir is not None:
        criteria.append(f"Full Gherkin: the `.feature` files under `{features_dir}/`.")
    parts = [
        [f"# Packet: {milestone.element['title']}"],
        [identity],
        _doc_section("## Scope", _scope_blocks(scope)),
        _doc_section("## Contract ring", [f"- `{e.ref}` — {e.element['title']}" for e in ring]),
        _doc_section("## Must hold", [f"- `{ref}`" for ref in packet.must_hold]),
        _doc_section("## May decide", [f"- {freedom}" for freedom in packet.may_decide]),
        _doc_section("## Unresolved", [f"- `{ref}`" for ref in packet.unresolved]),
        _doc_section("## Rejections", [f"- `{ref}`" for ref in packet.rejections]),
        _doc_section("## Criteria", criteria),
    ]
    return "\n\n".join("\n".join(part) for part in parts) + "\n"


def _doc_section(heading: str, body: list[str]) -> list[str]:
    """One section: heading, a blank line, then the body — ``(none)`` when the
    body is empty, per the module docstring's rule about absent obligations."""
    return [heading, "", *(body or ["(none)"])]


def _scope_blocks(elements: Sequence[PacketElement]) -> list[str]:
    """The Scope section's body: one block per element, a blank line between."""
    lines: list[str] = []
    for position, element in enumerate(elements):
        if position:
            lines.append("")
        lines += _element_block(element)
    return lines


def _element_block(element: PacketElement) -> list[str]:
    """One scope element at full fidelity: title heading, ref, its own fields
    in declaration order minus the heading four, prose last — ``show --format
    md``'s shape, so the two documents read the same way."""
    fields = element.element
    lines = [f"### {fields['title']}", "", f"`{element.ref}`"]
    lines += [
        f"- {name}: {_value_text(value)}"
        for name, value in fields.items()
        if name not in ("id", "title", "source", "body") and value not in ("", None, [])
    ]
    if body := fields["body"]:
        lines += ["", str(body).rstrip()]
    return lines


def _criterion_text(criterion: Criterion) -> str:
    """One criterion as a bullet: behavioural as its given/when/then clauses
    on one line, the other kinds by their statement. This is the index of the
    bar; the full Gherkin is the ``.feature`` files' job."""
    if criterion.statement:
        return f"- `{criterion.id}` ({criterion.kind.value}) — {criterion.statement}"
    clauses = []
    if criterion.given:
        clauses.append("given " + ", ".join(criterion.given))
    clauses.append("when " + criterion.when)
    clauses.append("then " + ", ".join(criterion.then))
    return f"- `{criterion.id}` — " + "; ".join(clauses)


# --- the site --------------------------------------------------------------------


def generate_site(
    design: Design, out: Path, *, today: date, scope: str | None = None
) -> tuple[Path, ...]:
    """Write the read-only site for ``design`` under ``out``; every page it wrote.

    Four page families: one page per element — ``ab show``'s neighbourhood,
    reused rather than re-derived, so a page and a terminal view can never
    disagree — an index grouping elements by kind, a traceability page
    rendering ``ab trace``'s paths per requirement, and a gaps page from the
    worklist. ``today`` is injected, not read: nothing between the store and
    the bytes reads a clock, which is what makes the site byte-deterministic.

    ``scope`` restricts every page to the subtree reachable from that ref by
    following refs outward — ``contains`` primarily, the containment tree,
    plus every other edge the ``Index`` already hands out: a component's own
    mini-site. Reachability rather than containment alone is also what keeps
    the site link-consistent under scoping: every ref an in-scope page points
    at is in scope by construction, so it has a page to link to.

    Raises ``UnknownRefError`` for a scope ref no element has, like ``show``
    and ``trace`` do for theirs.
    """
    index = Index.from_design(design)
    if scope is not None and scope not in index.by_id:
        raise UnknownRefError(
            f"unknown --scope ref {scope!r}: no element in this store has that id"
        )
    site = _Site(
        design=design,
        index=index,
        out=out,
        scope=subtree(index, scope) if scope is not None else frozenset(index.by_id),
        today=today,
    )
    return site.write()


@dataclass(frozen=True, slots=True)
class _Site:
    """One site generation run: the design, its index, the pages in scope and
    where they go. A dataclass because every page builder needs the same five
    facts, and a parameter list that long would be the same coupling in
    disguise."""

    design: Design
    index: Index
    out: Path
    scope: frozenset[Ref]
    today: date

    def write(self) -> tuple[Path, ...]:
        """Render and write every page: the whole-store views first, then one
        page per in-scope element in id order — the order they land in, and
        the order a caller can hold them to."""
        pages: list[tuple[str, str]] = [
            ("index.html", self._index_page()),
            ("gaps.html", self._gaps_page()),
            ("trace.html", self._trace_page()),
        ]
        pages += [
            (_page_path(ref), self._element_page(_neighbourhood(self.index, ref, depth=1)))
            for ref in sorted(self.scope)
        ]
        written: list[Path] = []
        for relative, html in pages:
            path = self.out / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
            written.append(path)
        return tuple(written)

    def _ref(self, ref: str, levels: int) -> str:
        """A ref as a link to its page when this site holds one, plain code
        when it does not — the one rule that keeps a scoped site internally
        link-consistent."""
        if ref in self.scope:
            return f'<a href="{_rel(_page_path(ref), levels)}">{escape(ref)}</a>'
        return f"<code>{escape(ref)}</code>"

    def _nav(self, levels: int) -> str:
        """The three whole-store views, linked from any page's depth."""
        links = [
            f'<a href="{_rel("index.html", levels)}">index</a>',
            f'<a href="{_rel("gaps.html", levels)}">gaps</a>',
            f'<a href="{_rel("trace.html", levels)}">traceability</a>',
        ]
        return "<p>" + " · ".join(links) + "</p>"

    def _index_page(self) -> str:
        body = [self._nav(0), f"<h1>{escape(self.design.system.title)}</h1>"]
        for kind, elements in self._groups():
            body.append(f"<h2>{escape(kind)}</h2>")
            body.append("<ul>")
            body += [f"<li>{self._ref(e.id, 0)} — {escape(e.title)}</li>" for e in elements]
            body.append("</ul>")
        return _page(self.design.system.title, "\n".join(body))

    def _groups(self) -> list[tuple[str, list[Element]]]:
        """In-scope elements grouped by their id's kind prefix: kinds in the
        order ``Index`` holds them — ``Design`` field order, the order the
        store's kinds arrive in — and ids sorted within each group, ``ab
        list``'s own order."""
        groups: dict[str, list[Element]] = {}
        for element in self.index.by_id.values():
            if element.id in self.scope:
                groups.setdefault(element.id.partition(":")[0], []).append(element)
        return [
            (kind, sorted(elements, key=lambda element: element.id))
            for kind, elements in groups.items()
        ]

    def _element_page(self, view: Neighbourhood) -> str:
        element = view.element
        body = [
            self._nav(2),
            f"<h1>{escape(element.title)}</h1>",
            f"<p><code>{escape(element.id)}</code></p>",
        ]
        if fields := view._fields():
            body.append("<ul>")
            body += [
                f"<li>{escape(name)}: {escape(_value_text(value))}</li>" for name, value in fields
            ]
            body.append("</ul>")
        if view.observations:
            # The same line the text format prints, the page's own spelling of
            # the show view it reuses.
            body += ["<h2>Observations</h2>", "<ul>"]
            body += [
                f"<li><code>{escape(_observation_line(observation))}</code></li>"
                for observation in view.observations
            ]
            body.append("</ul>")
        if points := self._hop_list(view.outgoing, levels=2):
            body += ["<h2>Points at</h2>", points]
        if incoming := view.incoming:
            body += ["<h2>Referenced by</h2>", "<ul>"]
            body += [
                f"<li>{self._ref(link.other.id, 2)} — {escape(link.field)}</li>"
                for link in incoming
            ]
            body.append("</ul>")
        if element.body:
            body += ["<h2>Body</h2>", _body_html(element.body)]
        return _page(element.title, "\n".join(body))

    def _hop_list(self, hops: tuple[Hop, ...], *, levels: int) -> str:
        """The outgoing side as nested lists, one list level per hop depth —
        the distance-from-focus the markdown view indents by."""
        if not hops:
            return ""
        items = [
            f"<li>{self._ref(hop.other.id, levels)} — {escape(hop.field)}"
            f"{self._hop_list(hop.deeper, levels=levels)}</li>"
            for hop in hops
        ]
        return "<ul>" + "\n".join(items) + "</ul>"

    def _gaps_page(self) -> str:
        gaps = [
            gap for gap in worklist(self.design, today=self.today) if gap.element.id in self.scope
        ]
        body = [self._nav(0), "<h1>Gaps</h1>"]
        if not gaps:
            body.append("<p>no gaps — nothing unfinished, nothing unowned, nothing expired</p>")
        else:
            body.append("<ul>")
            body += [
                f"<li>{self._ref(gap.element.id, 0)} — {escape(_attribution(gap))}"
                f" — {escape(gap.element.title)}</li>"
                for gap in gaps
            ]
            body.append("</ul>")
        return _page("Gaps", "\n".join(body))

    def _trace_page(self) -> str:
        """Traceability as ``ab trace`` spells it, one section per requirement
        — the kind the spec's own example chain starts from. Stories and NFRs
        trace too; a section per kind is a step this task does not need."""
        body = [self._nav(0), "<h1>Traceability</h1>"]
        requirements = sorted(ref for ref in self.scope if ref.startswith("requirement:"))
        for ref in requirements:
            traced = trace_paths(self.design, ref)
            body.append(f"<h2>{self._ref(ref, 0)} — {escape(self.index.by_id[ref].title)}</h2>")
            body += [f"<p>{self._path_line(ref, path)}</p>" for path in traced.paths]
            if traced.cycle_hit:
                body.append(
                    "<p>a cycle was hit; paths stop at the first repeat rather than looping</p>"
                )
        if not requirements:
            body.append("<p>no requirements in scope</p>")
        return _page("Traceability", "\n".join(body))

    def _path_line(self, start: Ref, path: tuple[Step, ...]) -> str:
        """One path, both directions' arrows — the HTML face of the line
        ``Trace.render_text`` prints, with every ref linked to its page."""
        parts = [self._ref(start, 0)]
        for step in path:
            parts.append(f" ←{step.field}— " if step.up else f" —{step.field}→ ")
            parts.append(self._ref(step.ref, 0))
        return "".join(parts)


def _page_path(ref: Ref) -> str:
    """A ref's page as a path from the site root: the id's kind as a
    directory, its slug as the file — one directory per kind, like the
    store."""
    kind, _, slug = ref.partition(":")
    return f"elements/{kind}/{slug}.html"


def _rel(target: str, levels: int) -> str:
    """A site-root-relative path as seen from a page ``levels`` directories
    down: the whole-store pages sit at the root, element pages two levels
    under it."""
    return "../" * levels + target


def _page(title: str, body: str) -> str:
    """The one HTML skeleton every page wears: static, valid, framework-free."""
    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            f"<title>{escape(title)}</title>",
            "</head>",
            "<body>",
            body,
            "</body>",
            "</html>",
            "",
        ]
    )


def _body_html(body: str) -> str:
    """Prose as HTML: headings and paragraphs, the subset the store's bodies
    use. ``body`` is carried verbatim and never parsed as design data — this
    is the one place it gets a shape, and deliberately the smallest one."""
    parts: list[str] = []
    for block in re.split(r"\n\s*\n", body.strip()):
        if block.startswith("#"):
            level = min(len(block) - len(block.lstrip("#")), 6)
            parts.append(f"<h{level}>{escape(block[level:].strip())}</h{level}>")
        else:
            parts.append(f"<p>{escape(block)}</p>")
    return "\n".join(parts)


# --- the preview server --------------------------------------------------------------


def store_snapshot(root: Path) -> dict[str, int]:
    """Every file under ``root`` with its mtime — the poll loop's cheap 'what
    changed since the last render' key. Generated output under the store
    (``build/``) is included on purpose: it only moves when the store does,
    and teaching this function the store's layout would be the coupling the
    layer stack exists to avoid."""
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def store_changed(root: Path, snapshot: dict[str, int]) -> bool:
    """Whether the store moved since ``snapshot`` was taken — the rebuild
    decision, split out from the loop that polls it so it can be tested
    without timing."""
    return store_snapshot(root) != snapshot


class SiteServer:
    """A local preview over a generated site: a threading ``http.server`` on
    the ``out`` directory, plus the poll-rebuild loop.

    ``watch`` and ``rebuild`` together arm rebuild-on-change: the watched
    tree's file mtimes are snapshotted, re-checked every ``interval`` seconds,
    and a change triggers one rebuild before the next snapshot. Polling, not
    filesystem events — proportionate for a store this size
    (docs/tasks/26-render-site.md). A rebuild that raises is logged and
    swallowed: a half-saved edit must not take the preview down with it.
    """

    def __init__(
        self,
        out: Path,
        port: int,
        *,
        watch: Path | None = None,
        rebuild: Callable[[], object] | None = None,
        interval: float = 1.0,
    ) -> None:
        handler = partial(SimpleHTTPRequestHandler, directory=str(out))
        # 127.0.0.1, not all interfaces: a preview is for the machine it was
        # started on, and it serves a read-only copy of the design either way.
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.port: int = self._httpd.server_address[1]
        self._watch = watch
        self._rebuild = rebuild
        self._interval = interval
        self._stop = threading.Event()

    def start(self) -> None:
        """Serve from daemon threads, so they die with the process however it
        ends — a preview should never outlive its terminal."""
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        if self._watch is not None and self._rebuild is not None:
            threading.Thread(target=self._poll, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._httpd.shutdown()
        self._httpd.server_close()

    def serve(self) -> None:
        """Block until stopped — the ``--serve`` main loop. A KeyboardInterrupt
        is the caller's way out, and lands in this wait."""
        self.start()
        try:
            self._stop.wait()
        finally:
            self.stop()

    def _poll(self) -> None:
        if self._watch is None or self._rebuild is None:
            return
        snapshot = store_snapshot(self._watch)
        while not self._stop.wait(self._interval):
            if store_changed(self._watch, snapshot):
                try:
                    self._rebuild()
                except Exception as exc:
                    log.warning("rebuild failed, serving the previous site: %s", exc)
                snapshot = store_snapshot(self._watch)
