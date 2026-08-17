"""Assemble the ``Packet`` an agent is handed: the brief for one milestone.

``ab packet``'s core (docs/tasks/31-packet-assembly.md and
57-packet-behaviors.md), below the CLI that renders it: given an
already-resolved ``Design`` and its ``Index``, select what an implementer
needs and nothing they do not —

- the milestone itself and everything in ``Milestone.scope`` at
  ``Fidelity.FULL`` — the element as built, every field;
- ``horizon`` rings of graph neighbours outward from scope, both edge
  directions (what scope consumes and what consumes it), each ring at
  ``Fidelity.CONTRACT`` — "the seam, nothing behind it";
- the behaviors (57): ``satisfy`` as the milestone's ``includes`` filtered to
  ``behavior:`` refs — the new work — and ``must_not_break`` as the active
  behaviors whose observations touch scope, the standing expectations whose
  breaking is a regression. Both enter ``elements`` at ``Fidelity.FULL`` with
  their observations, and each carries the effective timing beside the
  authored one, so a consumer of the packet never computes a default. What an
  included behavior composes joins the same way, one hop and no further;
  superseded behaviors join nothing (§5: they stop being packet input);
- the obligations and fences: ``must_hold`` (decisions and NFRs touching
  scope, plus whatever the milestone names), ``may_decide`` and ``unresolved``
  from the milestone, the ``rejections`` that must not be re-proposed, and the
  criteria the packet is done under.

Which fields count as "the contract" of a neighbouring element is a design
call the spec leaves open. This is it, written down once so it is not
re-litigated per bug report:

==================  ==========================  ===========================
kind                dropped at CONTRACT         why
==================  ==========================  ===========================
Component           contains, owns_data,         nesting, private data and
                    implemented_by               code pointers are behind
                                                the component's surface
every other kind    nothing                     a seam *is* its style,
                                                provider and failure modes;
                                                an external is our
                                                assumptions about a third
                                                party; a data entity is the
                                                shape crossing the boundary;
                                                the narrative kinds carry
                                                their meaning in prose as
                                                much as in typed fields
==================  ==========================  ===========================

A component is the one kind whose typed fields reach behind its own surface;
everything else it keeps (responsibility, provides, consumes) is the surface.
``source`` is always kept, at either fidelity: the packet stays traceable to
the store it was assembled from.

Failure vocabulary reuses ``absicht.findings`` rather than inventing a third
one. A broken invocation — no such milestone, an ``--include`` naming nothing,
the same ref included and excluded — raises ``PacketUsageError`` for the CLI
to map to ``ExitCode.USAGE``. A milestone that exists but names no scope
raises ``PacketFindingError`` carrying a ``packet/empty-scope`` finding: the
milestone is unusable as a packet target, which is a true statement about the
design (``ExitCode.FINDINGS``), not a broken invocation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from absicht.findings import RULES, Finding, Severity, finding
from absicht.models import (
    Behavior,
    Component,
    Criterion,
    CriterionId,
    Design,
    Element,
    Fidelity,
    Lifecycle,
    Milestone,
    Packet,
    PacketElement,
    Ref,
)
from absicht.resolve import Index, composes, effective_timing, touches

RULES["packet/empty-scope"] = (
    "A milestone that names no scope: there is nothing an agent may touch, so "
    "no packet can be assembled for it. Fix the milestone — or point ab packet "
    "at one that has a scope. A finding about the design, not a usage error."
)

# The kinds whose typed fields reach behind their own surface; see the table
# in the module docstring. Exact type, not isinstance: records are closed.
_BEHIND_THE_SEAM: dict[type[Element], frozenset[str]] = {
    Component: frozenset({"contains", "owns_data", "implemented_by"}),
}


class PacketUsageError(Exception):
    """A broken invocation. The CLI maps this to ``ExitCode.USAGE``."""


class PacketFindingError(Exception):
    """A true statement about the design that stops assembly. The CLI maps
    this to ``ExitCode.FINDINGS``; the finding rides along whole, for whatever
    report shape the caller renders."""

    def __init__(self, finding: Finding) -> None:
        super().__init__(finding.message)
        self.finding = finding


def assemble(
    design: Design,
    index: Index,
    milestone: Ref,
    *,
    horizon: int,
    include: frozenset[Ref],
    exclude: frozenset[Ref],
) -> Packet:
    """Assemble ``milestone``'s brief out of an already-resolved design.

    ``index`` must be ``Index.from_design(design)``: the enumeration that
    built the index is what "a neighbour" means here. ``include``/``exclude``
    are applied after the horizon computation — a forced-in element lands at
    ``Fidelity.FULL``, an excluded one is dropped — and shape only which
    *elements* the packet carries; the obligations are derived from the
    milestone's own fields either way. A scope or ring ref no element defines
    is skipped rather than raised on: dangling refs are ``ab check``'s
    finding, not a reason to refuse a packet.
    """
    target = index.by_id.get(milestone)
    if not isinstance(target, Milestone):
        raise PacketUsageError(f"{milestone} does not name a milestone in the design")
    if clash := include & exclude:
        both = ", ".join(sorted(clash))
        raise PacketUsageError(f"the same ref cannot be both included and excluded: {both}")
    if dangling := sorted(ref for ref in include if ref not in index.by_id):
        raise PacketUsageError(f"include names no element in the design: {', '.join(dangling)}")
    if not target.scope:
        raise PacketFindingError(
            finding(
                "packet/empty-scope",
                severity=Severity.ERROR,
                message=f"{milestone} names no scope: there is nothing an agent may touch",
                ref=milestone,
                source=target.source or None,
            )
        )

    core = frozenset(target.scope) | {milestone}
    selected: dict[Ref, Fidelity] = dict.fromkeys(core, Fidelity.FULL)
    selected |= dict.fromkeys(_rings(index, target.scope, horizon, core), Fidelity.CONTRACT)
    selected |= dict.fromkeys(include, Fidelity.FULL)
    satisfy = tuple(ref for ref in target.includes if ref.startswith("behavior:"))
    must_not_break = _must_not_break(design, target, satisfy=frozenset(satisfy))
    # Behaviors are the work and the guardrails: full fidelity, promoted over
    # any contract-ring entry the horizon may already have found them at.
    selected |= dict.fromkeys(
        (*satisfy, *must_not_break, *_composed(index, (*satisfy, *must_not_break))), Fidelity.FULL
    )
    for ref in exclude:
        selected.pop(ref, None)

    # In Design element order — load order — so the same store assembles to
    # the same packet; set iteration order would not promise that.
    elements = tuple(
        PacketElement(ref=ref, fidelity=fidelity, element=_carried(element, fidelity, index))
        for ref, element in index.by_id.items()
        if (fidelity := selected.get(ref)) is not None
    )
    return Packet(
        milestone=milestone,
        outcome=target.outcome,
        elements=elements,
        satisfy=satisfy,
        must_not_break=must_not_break,
        must_hold=_must_hold(design, target),
        may_decide=target.may_decide,
        unresolved=_unresolved(design, target),
        rejections=_rejections(design, target),
        criteria=_criteria(design, target),
    )


def _rings(index: Index, scope: tuple[Ref, ...], horizon: int, inside: frozenset[Ref]) -> set[Ref]:
    """``horizon`` rings of neighbours outward from scope, both edge directions.

    Each ring grows from the last. Everything already ``inside`` — scope, the
    milestone, earlier rings — is not re-entered, and a neighbour no element
    defines is skipped: a dangling ref has no fidelity to carry."""
    ring: set[Ref] = set()
    frontier: set[Ref] = set(scope)
    for _ in range(horizon):
        neighbours: set[Ref] = set()
        for ref in frontier:
            neighbours.update(edge.source for edge in index.referenced_by.get(ref, ()))
            neighbours.update(edge.target for edge in index.references_from.get(ref, ()))
        frontier = {ref for ref in neighbours if ref in index.by_id and ref not in inside}
        inside = inside | frontier
        ring |= frontier
    return ring


def _must_not_break(
    design: Design, milestone: Milestone, *, satisfy: frozenset[Ref]
) -> tuple[Ref, ...]:
    """§5's second and more valuable list: every active behavior whose
    observations touch the milestone's scope — the mechanical form of "do not
    regress the rest of the system" — minus the must-satisfy set, which is the
    new work, not a standing expectation about itself. Superseded behaviors
    never appear: §5 says a superseded behavior stops being packet input.
    Design order, so the same store assembles the same list."""
    scope = frozenset(milestone.scope)
    return tuple(
        behavior.id
        for behavior in design.behaviors
        if behavior.lifecycle is Lifecycle.ACTIVE
        and behavior.id not in satisfy
        and scope & set(touches(behavior))
    )


def _composed(index: Index, included: tuple[Ref, ...]) -> tuple[Ref, ...]:
    """§4.2's one-hop rule: for each behavior the packet includes — satisfy or
    must-not-break — the behaviors its observations assert occur join the
    packet with their own observations; what *those* compose in turn stays the
    reference inside an observation, never an element. Depth is measured from
    each included behavior, so a behavior two hops from one root still joins
    when another root composes it directly.

    The visited set is the same discipline ``trace`` holds: ``check`` may not
    have run, and a composition cycle must terminate the walk, not the
    command. A composed ref that names no active behavior — dangling, or
    superseded, which §5 stops being packet input — resolves to nothing here.
    """
    joined: dict[Ref, None] = {}
    visited: set[Ref] = set(included)
    for ref in included:
        behavior = index.by_id.get(ref)
        if not isinstance(behavior, Behavior):
            # An includes ref naming nothing: check's dangling-ref finding,
            # not a reason to refuse the packet.
            continue
        for composed in composes(behavior):
            target = index.by_id.get(composed)
            if (
                composed not in visited
                and isinstance(target, Behavior)
                and target.lifecycle is Lifecycle.ACTIVE
            ):
                visited.add(composed)
                joined[composed] = None
    return tuple(joined)


def _must_hold(design: Design, milestone: Milestone) -> tuple[Ref, ...]:
    """The milestone's own refs first, then intersecting decisions and NFRs —
    the two sources unioned, not either one picked."""
    scope = frozenset(milestone.scope)
    derived: list[Ref] = [d.id for d in design.decisions if scope & set(d.applies_to)]
    derived += [n.id for n in design.non_functionals if scope & set(n.scope)]
    return _dedup((*milestone.must_hold, *derived))


def _unresolved(design: Design, milestone: Milestone) -> tuple[Ref, ...]:
    """Open questions knowingly left open: the milestone's own, plus the ones
    blocking scope — the packet tells the agent about them rather than hiding
    them behind the milestone's silence."""
    scope = frozenset(milestone.scope)
    blocking = (q.id for q in design.questions if scope & set(q.blocks))
    return _dedup((*milestone.unresolved, *blocking))


def _rejections(design: Design, milestone: Milestone) -> tuple[Ref, ...]:
    """Rejections that must not be re-proposed: those applying to scope, plus
    those this milestone already lived through. Walking the design's own tuple
    in order is the dedup."""
    scope = frozenset(milestone.scope)
    return tuple(
        rejection.id
        for rejection in design.rejections
        if scope & set(rejection.applies_to) or rejection.milestone == milestone.id
    )


def _criteria(design: Design, milestone: Milestone) -> tuple[Criterion, ...]:
    """The bar the packet is done under: ``done_when`` first, then the
    acceptance of every story the milestone includes, deduplicated by id."""
    by_story = {story.id: story for story in design.stories}
    every = {criterion.id: criterion for story in design.stories for criterion in story.acceptance}
    chosen: dict[CriterionId, Criterion] = {}
    for criterion_id in milestone.done_when:
        # done_when can name a criterion of a story the milestone does not
        # include; one that names nothing is check's dangling-ref finding.
        if criterion_id in every:
            chosen[criterion_id] = every[criterion_id]
    for ref in milestone.includes:
        if (story := by_story.get(ref)) is not None:
            for criterion in story.acceptance:
                chosen.setdefault(criterion.id, criterion)
    return tuple(chosen.values())


def _carried(element: Element, fidelity: Fidelity, index: Index) -> dict[str, object]:
    """The element as the packet carries it: the full dump at ``FULL``; at
    ``CONTRACT``, minus the fields the module's table names as behind the
    seam. ``mode="json"`` keeps the dump serializable as-is. A behavior's
    observations additionally carry their effective timing beside the authored
    one — additive, like ``show``'s json — so a consumer of the packet never
    computes §1.2's default themselves."""
    carried = element.model_dump(mode="json")
    if isinstance(element, Behavior):
        entries = cast("list[dict[str, object]]", carried["observations"])
        for observation, entry in zip(element.observations, entries, strict=True):
            timing = effective_timing(index, observation)
            entry["effective_timing"] = timing.value if timing is not None else None
    if fidelity is Fidelity.CONTRACT:
        for field in _BEHIND_THE_SEAM.get(type(element), frozenset()):
            # `del`, not a defaulted pop: the dump always carries every field,
            # so a KeyError here means the table above has drifted from the
            # model — worth failing loudly on, not silently keeping.
            del carried[field]
    return carried


def _dedup(refs: Iterable[Ref]) -> tuple[Ref, ...]:
    """First occurrence wins — the union rule for every ref list the packet
    carries."""
    return tuple(dict.fromkeys(refs))
