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
- The criteria union: ``done_when`` (which may name a story the milestone does
  not include) plus the acceptance of the included stories, deduplicated.
- A milestone with no scope is a finding about the design, not a usage error:
  the milestone exists, it is just unusable as a packet target.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from absicht.findings import Severity
from absicht.load import load_store
from absicht.models import (
    Component,
    Criterion,
    Decision,
    Design,
    Fidelity,
    Milestone,
    NonFunctional,
    Packet,
    QualityAttribute,
    Question,
    Rejection,
    Seam,
    SeamStyle,
    Story,
    System,
)
from absicht.packet import PacketFindingError, PacketUsageError, assemble
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

    # Excluding something the packet never carried is a no-op, not an error:
    # there is nothing to drop.
    untouched = assemble(
        design,
        index,
        "milestone:m1",
        horizon=1,
        include=frozenset(),
        exclude=frozenset({"component:catalog"}),
    )
    assert "component:catalog" not in {e.ref for e in untouched.elements}
    assert len(untouched.elements) == 4


def test_a_ref_both_included_and_excluded_is_a_usage_error() -> None:
    design, index = _clean()

    with pytest.raises(PacketUsageError, match=r"component:catalog, seam:order-events"):
        assemble(
            design,
            index,
            "milestone:m1",
            horizon=1,
            include=frozenset({"seam:order-events", "component:catalog"}),
            exclude=frozenset({"seam:order-events", "component:catalog"}),
        )


def test_an_include_naming_no_element_is_a_usage_error() -> None:
    design, index = _clean()

    with pytest.raises(PacketUsageError, match=r"component:ghost, seam:ghost"):
        assemble(
            design,
            index,
            "milestone:m1",
            horizon=1,
            include=frozenset({"seam:ghost", "component:ghost"}),
            exclude=frozenset(),
        )


@pytest.mark.parametrize("ref", ["milestone:nope", "component:catalog"])
def test_a_milestone_argument_that_is_no_milestone_is_a_usage_error(ref: str) -> None:
    design, index = _clean()

    with pytest.raises(PacketUsageError, match=rf"{ref}"):
        assemble(design, index, ref, horizon=1, include=frozenset(), exclude=frozenset())


def test_a_milestone_with_no_scope_is_a_finding_not_a_usage_error(tmp_path: Path) -> None:
    """The milestone exists but names nothing the agent may touch: a true
    statement about the design (`FINDINGS`), not a broken invocation. Loaded
    from a store rather than built inline, so the finding can name the file
    the milestone lives in — where a human goes to fix it."""

    store = tmp_path / "store"
    (store / "milestones").mkdir(parents=True)
    (store / "system.yaml").write_text("id: system:empty\ntitle: Empty\n", encoding="utf-8")
    (store / "milestones" / "empty.md").write_text(
        "---\nid: milestone:empty\ntitle: Empty\n---\n", encoding="utf-8"
    )
    design = resolve(load_store(store))

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
    assert excinfo.value.finding.source == "milestones/empty.md"
    # The exception's own message is the finding's message: the CLI echoes
    # `str(error)` to stderr, and that must be the sentence worth reading.
    assert str(excinfo.value) == excinfo.value.finding.message


def _union_store() -> Design:
    """One scope component and a milestone whose ref lists name half their
    content directly while the other half is reachable only by intersection —
    the two sources the spec says to union, separated so a missing side cannot
    hide behind the other. `decision:applies-both` is in both sources, so the
    dedup is visible too. Every kind also carries one element on the negative
    side, reachable by neither source, so a union that grabs everything cannot
    pass as one; and `story:other`'s criterion is named by `done_when` while
    the story itself is not included, so the criteria union is not just the
    includes loop."""
    core = "component:core"
    elsewhere = "component:elsewhere"
    return Design(
        system=System(id="system:union", title="Union"),
        stories=(
            Story(
                id="story:other",
                title="Other",
                acceptance=(
                    Criterion(
                        id="story:other#ac-1",
                        when="the other story runs",
                        then=("it is its own bar",),
                    ),
                ),
            ),
        ),
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
            NonFunctional(
                id="nfr:elsewhere",
                title="Scoped elsewhere",
                attribute=QualityAttribute.PRIVACY,
                scope=(elsewhere,),
            ),
        ),
        decisions=(
            Decision(
                id="decision:applies-both",
                title="Named by the milestone and applies to the core",
                applies_to=(core,),
            ),
            Decision(id="decision:derived", title="Applies to the core", applies_to=(core,)),
            Decision(id="decision:elsewhere", title="Applies elsewhere", applies_to=(elsewhere,)),
        ),
        questions=(
            Question(id="question:named", title="Named by the milestone"),
            Question(id="question:derived", title="Blocks the core", blocks=(core,)),
            Question(id="question:elsewhere", title="Blocks elsewhere", blocks=(elsewhere,)),
        ),
        rejections=(
            Rejection(id="rejection:applies", title="Applies to the core", applies_to=(core,)),
            Rejection(
                id="rejection:named", title="Rejected in this milestone", milestone="milestone:m"
            ),
            Rejection(
                id="rejection:elsewhere",
                title="Rejected in another milestone",
                milestone="milestone:other",
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
                done_when=("story:other#ac-1",),
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


def test_done_when_can_name_a_criterion_of_a_story_the_milestone_does_not_include() -> None:
    assert [c.id for c in _assembled_union().criteria] == ["story:other#ac-1"]


def test_the_second_ring_grows_through_elements_nothing_points_at() -> None:
    """Ring 1 over the union store is elements that point at scope and are
    pointed at by nothing; the second ring grows outward from them without
    assuming every frontier member has incoming references. It adds nothing —
    everything they point at is already inside."""
    design = _union_store()

    packet = assemble(
        design,
        Index.from_design(design),
        "milestone:m",
        horizon=2,
        include=frozenset(),
        exclude=frozenset(),
    )

    assert {e.ref: e.fidelity for e in packet.elements} == {
        "milestone:m": Fidelity.FULL,
        "component:core": Fidelity.FULL,
        "decision:applies-both": Fidelity.CONTRACT,
        "decision:derived": Fidelity.CONTRACT,
        "nfr:derived": Fidelity.CONTRACT,
        "question:derived": Fidelity.CONTRACT,
        "rejection:applies": Fidelity.CONTRACT,
    }


def test_a_scope_member_nothing_points_at_still_expands_outward() -> None:
    """Ring expansion reads both directions and must survive one of them being
    empty: a scope component with no incoming references still pulls in what it
    consumes."""
    design = Design(
        system=System(id="system:solo", title="Solo"),
        components=(Component(id="component:solo", title="Solo", consumes=("seam:feed",)),),
        seams=(Seam(id="seam:feed", title="Feed", style=SeamStyle.EVENT),),
        milestones=(Milestone(id="milestone:m", title="M", scope=("component:solo",)),),
    )

    packet = assemble(
        design,
        Index.from_design(design),
        "milestone:m",
        horizon=1,
        include=frozenset(),
        exclude=frozenset(),
    )

    assert {e.ref: e.fidelity for e in packet.elements} == {
        "milestone:m": Fidelity.FULL,
        "component:solo": Fidelity.FULL,
        "seam:feed": Fidelity.CONTRACT,
    }
