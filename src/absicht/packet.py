"""Assemble the packet for one milestone.

The selection, in one sentence: everything the agent may touch arrives whole,
everything it will meet at the boundary arrives as a contract, and everything
else does not arrive.

Whole (`Fidelity.FULL`)
    The milestone, its `scope`, the behaviors it `includes` and one hop of
    what they compose, the behaviors it must not break, the obligations in
    `must_hold`, the questions left `unresolved`, and the `rejections`. Each
    of those is read for its argument, not for its shape: a decision without
    its consequences and a rejection without its reason are both noise.

Contract (`Fidelity.CONTRACT`)
    Graph neighbours, `horizon` rings out, in both directions — what the
    scope calls and what calls the scope. One direction would be arbitrary.

Dropped at CONTRACT
    `implemented_by`, on every kind that has one. It is the only typed field
    that reaches behind an element's own surface, now that nesting is a
    `parent` on the child rather than a list on the parent. Everything else a
    neighbour carries is its surface: an interface is its operations, an
    external service is our assumptions about somebody else, a data entity is
    the shape that crosses. `source` survives both fidelities, so a packet
    stays traceable to the store it came from.

A superseded behavior joins nothing. It stopped being how the system works,
so handing it to an agent asks for the past to be rebuilt.

The failure vocabulary is `absicht.findings`, not a third one. A milestone
that exists but names no scope is a true statement about the design, so it is
a finding and not a usage error.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from absicht.findings import RULES, Finding, Severity, finding
from absicht.models.design import Behavior, Design, Element, Lifecycle, Milestone
from absicht.models.packet import Fidelity, Packet, PacketElement
from absicht.resolve import Index, composes, touches

RULES["packet/empty-scope"] = (
    "A milestone that names no scope: nothing says what an agent may touch, "
    "so no packet can be assembled from it. A finding about the design, not a "
    "broken invocation."
)

_BEHIND_THE_SURFACE = frozenset({"implemented_by"})
"""Dropped at CONTRACT. The one field that reaches past what a neighbour
publishes; everything else it carries is the reason to know about it."""


class PacketError(Exception):
    """Assembly could not produce a packet. Carries what to report."""

    def __init__(self, report: Finding) -> None:
        super().__init__(report.message)
        self.report = report


def _shape(element: Element, fidelity: Fidelity) -> dict[str, object]:
    body = element.model_dump(mode="json")
    if fidelity is Fidelity.CONTRACT:
        for field in _BEHIND_THE_SURFACE:
            body.pop(field, None)
    return body


def _behaviors_in_play(
    ix: Index, milestone: Milestone, scope: frozenset[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What the slice must satisfy, and what it must not break."""
    active = {b.id: b for b in ix.of_type(Behavior) if b.lifecycle is Lifecycle.ACTIVE}
    satisfy: list[str] = []
    for ref in milestone.includes:
        behavior = active.get(ref)
        if behavior is None:
            continue
        satisfy.append(ref)
        satisfy += [one for one in composes(behavior) if one in active]

    ordered_satisfy = tuple(dict.fromkeys(satisfy))
    must_not_break = tuple(
        ref
        for ref, behavior in active.items()
        if ref not in ordered_satisfy and touches(behavior, scope)
    )
    return ordered_satisfy, must_not_break


def assemble(
    design: Design,
    milestone_ref: str,
    *,
    imports: Mapping[str, Design] | None = None,
    horizon: int = 1,
    design_rev: str = "",
) -> Packet:
    """The packet for one milestone, or a `PacketError` saying why not."""
    ix = Index(design, imports)
    milestone = ix.get(milestone_ref)
    if not isinstance(milestone, Milestone):
        raise LookupError(f"{milestone_ref} is not a milestone of {design.id}")
    if not milestone.scope:
        raise PacketError(
            finding(
                "packet/empty-scope",
                severity=Severity.ERROR,
                message=f"{milestone.id} says nothing about what may be touched",
                ref=milestone.id,
                source=milestone.source or None,
            )
        )

    scope = frozenset(milestone.scope)
    satisfy, must_not_break = _behaviors_in_play(ix, milestone, scope)

    whole = frozenset(
        {milestone.id, *scope, *satisfy, *must_not_break}
        | set(milestone.must_hold)
        | set(milestone.unresolved)
        | {r.id for r in design.rejections}
    )
    surface = frozenset(ix.ring(whole, horizon))

    elements: list[PacketElement] = []
    for fidelity, refs in ((Fidelity.FULL, whole), (Fidelity.CONTRACT, surface)):
        for ref in sorted(refs):
            element = ix.get(ref)
            if element is None:
                continue  # a dangling ref is check's finding, not a packet's
            if element.lifecycle is Lifecycle.SUPERSEDED:
                continue  # it stopped being how the system works
            elements.append(
                PacketElement(
                    ref=ref,
                    fidelity=fidelity,
                    element=_shape(element, fidelity),
                )
            )

    return Packet(
        milestone=milestone.id,
        design=design.id,
        design_rev=design_rev,
        outcome=milestone.outcome,
        elements=tuple(elements),
        satisfy=satisfy,
        must_not_break=must_not_break,
        must_hold=milestone.must_hold,
        may_decide=milestone.may_decide,
        unresolved=milestone.unresolved,
        rejections=tuple(r.id for r in design.rejections),
        done_when=milestone.done_when,
    )


def summarise(packet: Packet) -> Iterator[str]:
    """One line per packet element, for a human reading a diff of one."""
    for entry in packet.elements:
        yield f"{entry.fidelity.value:8} {entry.ref}"
