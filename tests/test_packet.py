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
- The addendum's behavior content (docs/tasks/57-packet-behaviors.md):
  ``satisfy`` as ``includes`` filtered to behavior refs, ``must_not_break`` as
  the active behaviors touching scope minus satisfy (superseded never), the
  one-hop composition expansion, and the effective timing carried beside every
  observation so an agent never computes a default.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from absicht.findings import Severity
from absicht.load import load_store
from absicht.models import (
    Behavior,
    Component,
    Criterion,
    Decision,
    Design,
    Fidelity,
    Lifecycle,
    Milestone,
    NonFunctional,
    Observation,
    Outcome,
    Packet,
    QualityAttribute,
    Question,
    Rejection,
    Resource,
    ResourceKind,
    Seam,
    SeamStyle,
    Story,
    System,
    Timing,
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
        # The behaviors realize the requirement one ring in, so the second
        # ring carries them at contract fidelity — an agent working the scope
        # sees the expectations attached to the requirement it serves.
        "behavior:order-placed-v2": Fidelity.CONTRACT,
        "behavior:order-placed": Fidelity.CONTRACT,
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
    assert len(packet.elements) == 8  # the horizon-2 packet, minus the story

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


# --------------------------------------------- behaviors (docs/tasks/57)


def _assembled(design: Design, milestone: str) -> Packet:
    """``assemble`` over an inline design at the default horizon, nothing
    forced either way — the shape every behavior test below starts from."""
    return assemble(
        design,
        Index.from_design(design),
        milestone,
        horizon=1,
        include=frozenset(),
        exclude=frozenset(),
    )


def _behavior(
    behavior_id: str,
    *,
    at: tuple[str, ...],
    lifecycle: Lifecycle = Lifecycle.ACTIVE,
    observations: tuple[Observation, ...] = (),
) -> Behavior:
    """One behavior with a generated ``must`` observation per ``at`` ref,
    ``obs-N`` in the order authored — unless the test spells the observations
    itself, which the timing tests do because a generated one carries no
    authored timing to win with."""
    return Behavior(
        id=behavior_id,
        title=behavior_id.removeprefix("behavior:"),
        trigger=f"{behavior_id.removeprefix('behavior:')} happens.",
        lifecycle=lifecycle,
        observations=observations
        or tuple(
            Observation(
                id=f"{behavior_id}#obs-{position}",
                statement=f"observes {target}",
                at=target,
            )
            for position, target in enumerate(at, start=1)
        ),
    )


def _selection_store() -> Design:
    """One behavior on each side of the must-not-break rule: an active guard
    touching scope (in), an active behavior touching only elsewhere (out), a
    superseded one touching scope (out — §5 says it stops being packet input),
    and the must-satisfy behavior the milestone names (the work, never
    repeated as a standing expectation)."""
    core, elsewhere = "component:core", "component:elsewhere"
    return Design(
        system=System(id="system:selection", title="Selection"),
        components=(
            Component(id=core, title="Core"),
            Component(id=elsewhere, title="Elsewhere"),
        ),
        behaviors=(
            _behavior("behavior:guard", at=(core,)),
            _behavior("behavior:far", at=(elsewhere,)),
            _behavior("behavior:old", at=(core,), lifecycle=Lifecycle.SUPERSEDED),
            _behavior("behavior:new-work", at=(core,)),
        ),
        milestones=(
            Milestone(id="milestone:m", title="M", includes=("behavior:new-work",), scope=(core,)),
        ),
    )


def test_satisfy_is_the_milestones_includes_filtered_to_behavior_refs() -> None:
    assert _assembled(_selection_store(), "milestone:m").satisfy == ("behavior:new-work",)


def test_must_not_break_is_active_behaviors_touching_scope_minus_satisfy() -> None:
    packet = _assembled(_selection_store(), "milestone:m")

    # guard touches scope and is active: in. far touches only elsewhere: out.
    # old touches scope but is superseded: out. new-work is the satisfy set
    # itself, not a standing expectation about work it is doing: out.
    assert packet.must_not_break == ("behavior:guard",)


def test_the_behavior_lists_enter_elements_at_full_fidelity_with_observations() -> None:
    packet = _assembled(_selection_store(), "milestone:m")
    by_ref = {element.ref: element for element in packet.elements}

    # Observations included: the satisfy list is the work, and an expectation
    # that may not be broken is only actionable verbatim.
    assert by_ref["behavior:new-work"].fidelity is Fidelity.FULL
    assert by_ref["behavior:guard"].fidelity is Fidelity.FULL
    assert [obs["id"] for obs in by_ref["behavior:guard"].element["observations"]] == [
        "behavior:guard#obs-1"
    ]
    # A superseded behavior stays what the ring made it — contract context,
    # never behavior content — even though it touches scope like the guard.
    assert by_ref["behavior:old"].fidelity is Fidelity.CONTRACT


def _chain_store() -> Design:
    """The addendum's own A→B→C: the milestone selects A, A composes B, B
    composes C, and C touches nothing in scope — so the packet carries A and B
    with observations and references C without expanding it."""
    return Design(
        system=System(id="system:chain", title="Chain"),
        components=(
            Component(id="component:core", title="Core"),
            Component(id="component:away", title="Away"),
        ),
        behaviors=(
            _behavior("behavior:a", at=("component:core", "behavior:b")),
            _behavior("behavior:b", at=("behavior:c",)),
            _behavior("behavior:c", at=("component:away",)),
        ),
        milestones=(
            Milestone(
                id="milestone:m", title="M", includes=("behavior:a",), scope=("component:core",)
            ),
        ),
    )


def test_composition_expands_exactly_one_hop_from_each_included_behavior() -> None:
    packet = _assembled(_chain_store(), "milestone:m")
    by_ref = {element.ref: element for element in packet.elements}

    assert packet.satisfy == ("behavior:a",)
    # B joins with its own observations although it touches nothing in scope —
    # one hop from A is reason enough. C, two hops from the root, does not
    # join, and no list claims it either.
    assert packet.must_not_break == ()
    assert by_ref["behavior:a"].fidelity is Fidelity.FULL
    assert by_ref["behavior:b"].fidelity is Fidelity.FULL
    assert "behavior:c" not in by_ref
    # C is still referenced — B's observation asserts it occurs — which is how
    # "references without expanding" survives serialization.
    assert [obs["at"] for obs in by_ref["behavior:b"].element["observations"]] == ["behavior:c"]


def _cycle_store() -> Design:
    """Composition cycles — the mutual X↔Y and the self-composing Z — which
    `ab check` reports and `ab packet` must survive: assembly walks possibly
    unchecked input and cannot hang on it."""
    return Design(
        system=System(id="system:cycle", title="Cycle"),
        components=(Component(id="component:core", title="Core"),),
        behaviors=(
            _behavior("behavior:x", at=("component:core", "behavior:y")),
            _behavior("behavior:y", at=("behavior:x",)),
            _behavior("behavior:z", at=("behavior:z",)),
        ),
        milestones=(
            Milestone(
                id="milestone:m",
                title="M",
                includes=("behavior:x", "behavior:z"),
                scope=("component:core",),
            ),
        ),
    )


def test_composition_cycles_terminate_instead_of_hanging() -> None:
    packet = _assembled(_cycle_store(), "milestone:m")

    assert packet.satisfy == ("behavior:x", "behavior:z")
    # Y joins once, one hop from X; X composing Y and Y composing X cannot
    # re-enter the walk, and Z's self-composition joins nothing new.
    assert packet.must_not_break == ()
    assert {element.ref: element.fidelity for element in packet.elements} == {
        "milestone:m": Fidelity.FULL,
        "component:core": Fidelity.FULL,
        "behavior:x": Fidelity.FULL,
        "behavior:y": Fidelity.FULL,
        "behavior:z": Fidelity.FULL,
    }


def _timing_store() -> Design:
    """Every row of §1.2's table plus the authored-wins rule, one observation
    each: a stream and a store left unsaid, an authored timing over the
    `immediate` default, and a `must_not` with no when at all."""
    return Design(
        system=System(id="system:timing", title="Timing"),
        components=(Component(id="component:core", title="Core"),),
        resources=(
            Resource(
                id="resource:events",
                title="Events",
                resource_kind=ResourceKind.STREAM,
                technology="Kafka",
            ),
            Resource(
                id="resource:db",
                title="Database",
                resource_kind=ResourceKind.STORE,
                technology="Postgres",
            ),
        ),
        behaviors=(
            Behavior(
                id="behavior:timed",
                title="Timed",
                trigger="Something happens.",
                observations=(
                    Observation(
                        id="behavior:timed#obs-1",
                        statement="unsaid, over a stream",
                        at="resource:events",
                    ),
                    Observation(
                        id="behavior:timed#obs-2",
                        statement="unsaid, over a store",
                        at="resource:db",
                    ),
                    Observation(
                        id="behavior:timed#obs-3",
                        statement="said, and it wins",
                        at="component:core",
                        timing=Timing.EVENTUAL,
                    ),
                    Observation(
                        id="behavior:timed#obs-4",
                        statement="never, at no point",
                        at="resource:db",
                        outcome=Outcome.MUST_NOT,
                    ),
                ),
            ),
        ),
        milestones=(
            Milestone(
                id="milestone:m", title="M", includes=("behavior:timed",), scope=("component:core",)
            ),
        ),
    )


def test_carried_observations_spell_their_effective_timing() -> None:
    packet = _assembled(_timing_store(), "milestone:m")

    behavior = next(element for element in packet.elements if element.ref == "behavior:timed")
    observations = behavior.element["observations"]

    assert [observation["effective_timing"] for observation in observations] == [
        "eventual",  # §1.2: a stream defaults eventual, asserted by consuming it
        "immediate",  # a store defaults immediate
        "eventual",  # an authored timing wins over the immediate default
        None,  # must_not means "at no point": no when to spell
    ]
    # The authored side stays what the file said — additive, never rewritten.
    assert [observation["timing"] for observation in observations] == [None, None, "eventual", None]


def test_no_note_ref_appears_anywhere_in_the_serialized_packet(tmp_path: Path) -> None:
    """§6: an agent never sees a note. Notes are structurally outside
    `Design`, so assembly cannot reach one — pinned against a store that
    actually carries a note pointed straight at the scope."""
    store = tmp_path / "store"
    (store / "components").mkdir(parents=True)
    (store / "milestones").mkdir()
    (store / "notes").mkdir()
    (store / "system.yaml").write_text("id: system:noted\ntitle: Noted\n", encoding="utf-8")
    (store / "components" / "core.md").write_text(
        "---\nid: component:core\ntitle: Core\n---\n", encoding="utf-8"
    )
    (store / "milestones" / "m.md").write_text(
        "---\nid: milestone:m\ntitle: M\nscope:\n- component:core\n---\n", encoding="utf-8"
    )
    (store / "notes" / "about-core.md").write_text(
        "---\nid: note:k1j2k3\nref: component:core\ncreated: 2026-08-16\n---\n"
        "The packet must never carry this.\n",
        encoding="utf-8",
    )

    packet = _assembled(resolve(load_store(store)), "milestone:m")

    assert "note:" not in packet.model_dump_json()


def test_the_same_design_and_milestone_assemble_identically() -> None:
    """§8's premise — the artifact is deterministic from milestone plus design
    rev — pinned at the source: two assemblies of one store agree byte for
    byte, lists included."""
    design = _selection_store()

    assert (
        _assembled(design, "milestone:m").model_dump_json()
        == _assembled(design, "milestone:m").model_dump_json()
    )
