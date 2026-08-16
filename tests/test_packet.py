"""``absicht.packet``: assemble the brief an agent is handed, per ``docs/tasks/31-packet-assembly.md``.

What these tests pin:

- The selection over ``clean/``'s milestone: scope plus the milestone itself
  at full fidelity, ``--horizon N`` rings of graph neighbours (both edge
  directions — "consume / are consumed by") at contract fidelity, in the
  design's own element order so the assembled packet is deterministic.
- The contract-field cut: a neighbouring component loses the fields that are
  behind its surface; kinds that are nothing but a contract keep everything.
- ``--include``/``--exclude`` applied after the horizon: a forced-in element
  lands at full fidelity, an excluded one is gone, and the same ref in both is
  a usage error, as is an ``--include`` naming nothing and a ``MILESTONE``
  argument that does not name a milestone.
- ``must_hold``/``unresolved``/``rejections`` as the union of the milestone's
  own field and the derived source, deduplicated — pinned against an inline
  store whose milestone names half of each list directly and leaves the other
  half reachable only by intersection, so a missing side cannot hide.
- A milestone with no scope is a finding about the design, not a usage error:
  the milestone exists, it is just unusable as a packet target.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from absicht.packet import PacketFindingError, PacketUsageError, assemble

from absicht.findings import Severity
from absicht.load import load_store
from absicht.models import (
    Component,
    Decision,
    Design,
    Fidelity,
    Milestone,
    NonFunctional,
    Packet,
    QualityAttribute,
    Question,
    Rejection,
    System,
)
from absicht.resolve import Index, resolve

CLEAN = Path(__file__).parent / "fixtures" / "systems" / "clean"


def _clean() -> tuple[Design, Index]:
    """The `clean` fixture as `assemble` consumes it: design plus its index."""
    design = resolve(load_store(CLEAN))
    return design, Index.from_design(design)


def test_horizon_one_carries_scope_and_milestone_at_full_and_one_ring_at_contract() -> None:
    design, index = _clean()

    packet = assemble(
        design, index, "milestone:m1", horizon=1, include=frozenset(), exclude=frozenset()
    )

    assert {e.ref: e.fidelity for e in packet.elements} == {
        "milestone:m1": Fidelity.FULL,
        "component:cancellation": Fidelity.FULL,
        "seam:order-events": Fidelity.CONTRACT,
        "requirement:cancel-orders": Fidelity.CONTRACT,
    }
    # Design element order, so the same store assembles to the same packet.
    assert [e.ref for e in packet.elements] == [
        "requirement:cancel-orders",
        "component:cancellation",
        "seam:order-events",
        "milestone:m1",
    ]
    assert packet.milestone == "milestone:m1"
    assert packet.outcome == "A customer can cancel a refundable order."


def test_horizon_two_adds_the_second_ring_still_at_contract() -> None:
    design, index = _clean()

    packet = assemble(
        design, index, "milestone:m1", horizon=2, include=frozenset(), exclude=frozenset()
    )

    assert {e.ref: e.fidelity for e in packet.elements} == {
        "milestone:m1": Fidelity.FULL,
        "component:cancellation": Fidelity.FULL,
        "seam:order-events": Fidelity.CONTRACT,
        "requirement:cancel-orders": Fidelity.CONTRACT,
        "component:orders": Fidelity.CONTRACT,
        "data:order": Fidelity.CONTRACT,
        "story:cancel-order": Fidelity.CONTRACT,
    }
    # The ring does not leak into the brief's obligations: `decision:event-log`
    # applies to component:orders, which is a neighbour, not scope.
    assert packet.must_hold == ()


def test_full_fidelity_carries_the_element_exactly_as_built() -> None:
    design, index = _clean()

    packet = assemble(
        design, index, "milestone:m1", horizon=1, include=frozenset(), exclude=frozenset()
    )

    by_ref = {e.ref: e for e in packet.elements}
    assert by_ref["component:cancellation"].element == index.by_id[
        "component:cancellation"
    ].model_dump(mode="json")
    assert by_ref["milestone:m1"].element == index.by_id["milestone:m1"].model_dump(mode="json")


def test_contract_fidelity_keeps_the_surface_and_drops_component_internals() -> None:
    design, index = _clean()

    packet = assemble(
        design, index, "milestone:m1", horizon=2, include=frozenset(), exclude=frozenset()
    )

    by_ref = {e.ref: e.element for e in packet.elements}
    # A component neighbour contributes its surface; nesting, owned data and
    # code pointers are what "the seam, nothing behind it" excludes.
    assert "responsibility" in by_ref["component:orders"]
    assert "provides" in by_ref["component:orders"]
    assert "consumes" in by_ref["component:orders"]
    assert "contains" not in by_ref["component:orders"]
    assert "owns_data" not in by_ref["component:orders"]
    assert "implemented_by" not in by_ref["component:orders"]
    # Kinds that are nothing but a contract keep everything they carry.
    assert "style" in by_ref["seam:order-events"]
    assert "failure_modes" in by_ref["seam:order-events"]
    assert "acceptance" in by_ref["story:cancel-order"]
    assert by_ref["requirement:cancel-orders"]["body"] == (
        "A customer may cancel an order while it can still be refunded."
    )


def test_include_forces_full_fidelity_even_outside_the_horizon() -> None:
    design, index = _clean()

    packet = assemble(
        design,
        index,
        "milestone:m1",
        horizon=1,
        include=frozenset({"component:catalog", "seam:order-events"}),
        exclude=frozenset(),
    )

    fidelities = {e.ref: e.fidelity for e in packet.elements}
    assert fidelities["component:catalog"] == Fidelity.FULL  # three rings out, forced in
    assert fidelities["seam:order-events"] == Fidelity.FULL  # in a ring, promoted


def test_exclude_drops_what_the_horizon_would_have_pulled_in() -> None:
    design, index = _clean()

    packet = assemble(
        design,
        index,
        "milestone:m1",
        horizon=2,
        include=frozenset(),
        exclude=frozenset({"story:cancel-order"}),
    )

    assert "story:cancel-order" not in {e.ref for e in packet.elements}
    assert len(packet.elements) == 6  # the horizon-2 packet, minus the story


def test_a_ref_both_included_and_excluded_is_a_usage_error() -> None:
    design, index = _clean()

    with pytest.raises(PacketUsageError, match=r"component:catalog"):
        assemble(
            design,
            index,
            "milestone:m1",
            horizon=1,
            include=frozenset({"component:catalog"}),
            exclude=frozenset({"component:catalog"}),
        )


def test_an_include_naming_no_element_is_a_usage_error() -> None:
    design, index = _clean()

    with pytest.raises(PacketUsageError, match=r"component:ghost"):
        assemble(
            design,
            index,
            "milestone:m1",
            horizon=1,
            include=frozenset({"component:ghost"}),
            exclude=frozenset(),
        )


@pytest.mark.parametrize("ref", ["milestone:nope", "component:catalog"])
def test_a_milestone_argument_that_is_no_milestone_is_a_usage_error(ref: str) -> None:
    design, index = _clean()

    with pytest.raises(PacketUsageError, match=rf"{ref}"):
        assemble(design, index, ref, horizon=1, include=frozenset(), exclude=frozenset())


def test_a_milestone_with_no_scope_is_a_finding_not_a_usage_error() -> None:
    """The milestone exists but names nothing the agent may touch: a true
    statement about the design (`FINDINGS`), not a broken invocation."""

    design = Design(
        system=System(id="system:empty", title="Empty"),
        milestones=(Milestone(id="milestone:empty", title="Empty"),),
    )

    with pytest.raises(PacketFindingError) as excinfo:
        assemble(
            design,
            Index.from_design(design),
            "milestone:empty",
            horizon=1,
            include=frozenset(),
            exclude=frozenset(),
        )

    assert excinfo.value.finding.rule_id == "packet/empty-scope"
    assert excinfo.value.finding.severity is Severity.ERROR
    assert excinfo.value.finding.ref == "milestone:empty"


def _union_store() -> Design:
    """One scope component and a milestone whose ref lists name half their
    content directly while the other half is reachable only by intersection —
    the two sources the spec says to union, separated so a missing side cannot
    hide behind the other. `decision:applies-both` is in both sources, so the
    dedup is visible too."""
    core = "component:core"
    return Design(
        system=System(id="system:union", title="Union"),
        components=(Component(id=core, title="Core"),),
        non_functionals=(
            NonFunctional(
                id="nfr:named", title="Named by the milestone", attribute=QualityAttribute.LATENCY
            ),
            NonFunctional(
                id="nfr:derived",
                title="Scoped to the core",
                attribute=QualityAttribute.COST,
                scope=(core,),
            ),
        ),
        decisions=(
            Decision(
                id="decision:applies-both",
                title="Named by the milestone and applies to the core",
                applies_to=(core,),
            ),
            Decision(id="decision:derived", title="Applies to the core", applies_to=(core,)),
        ),
        questions=(
            Question(id="question:named", title="Named by the milestone"),
            Question(id="question:derived", title="Blocks the core", blocks=(core,)),
        ),
        rejections=(
            Rejection(id="rejection:applies", title="Applies to the core", applies_to=(core,)),
            Rejection(
                id="rejection:named", title="Rejected in this milestone", milestone="milestone:m"
            ),
        ),
        milestones=(
            Milestone(
                id="milestone:m",
                title="M",
                scope=(core,),
                must_hold=("decision:applies-both", "nfr:named"),
                may_decide=("the refund timing",),
                unresolved=("question:named",),
            ),
        ),
    )


def _assembled_union() -> Packet:
    design = _union_store()
    return assemble(
        design,
        Index.from_design(design),
        "milestone:m",
        horizon=1,
        include=frozenset(),
        exclude=frozenset(),
    )


def test_must_hold_unions_the_milestones_own_refs_with_intersecting_decisions_and_nfrs() -> None:
    """The milestone's own naming first, then intersecting decisions and NFRs,
    deduplicated: `decision:applies-both` is named and intersects, and must
    not appear twice."""

    assert _assembled_union().must_hold == (
        "decision:applies-both",
        "nfr:named",
        "decision:derived",
        "nfr:derived",
    )


def test_rejections_come_from_intersection_and_from_the_milestones_own_field() -> None:
    assert _assembled_union().rejections == ("rejection:applies", "rejection:named")


def test_unresolved_unions_the_milestones_own_questions_with_those_blocking_scope() -> None:
    assert _assembled_union().unresolved == ("question:named", "question:derived")


def test_may_decide_is_the_milestones_own_list_verbatim() -> None:
    assert _assembled_union().may_decide == ("the refund timing",)


def test_criteria_union_done_when_and_the_included_stories_acceptance() -> None:
    design, index = _clean()

    packet = assemble(
        design, index, "milestone:m1", horizon=1, include=frozenset(), exclude=frozenset()
    )

    assert [c.id for c in packet.criteria] == [
        "story:cancel-order#ac-1",
        "story:cancel-order#ac-2",
        "story:cancel-order#ac-3",
    ]
    assert packet.criteria == design.stories[0].acceptance
