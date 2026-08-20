"""``absicht.packet``: the brief an agent is handed, assembled from one milestone.

The selection is the whole value of a packet, so what these tests pin is the
selection and the refusals, never the rendering (``tests/test_packet_cli.py``
owns that):

- the fidelity split. What the agent may touch arrives whole — the milestone,
  its ``scope``, the behaviors it ``includes``, the obligations in
  ``must_hold``, the questions left ``unresolved`` and the ``rejections`` —
  what it will meet at the boundary arrives as a contract, ``horizon`` rings
  out in *both* edge directions, and everything else does not arrive;
- what a contract drops: ``implemented_by`` and nothing else. Everything a
  neighbour else carries is its surface, and ``source`` survives both
  fidelities so a packet stays traceable to the store it came from;
- ``satisfy`` as the milestone's ``includes`` filtered to active behaviors,
  expanded exactly one hop through composition, and ``must_not_break`` as the
  active behaviors touching scope that are not already the work;
- a superseded behavior joins nothing — not the work, not the standing
  expectations, not even the contract ring: it stopped being how the system
  works, so handing it over asks for the past to be rebuilt;
- the two refusals and the difference between them: a ref that names no
  milestone is a broken invocation (``LookupError``), while a milestone that
  names no scope is a true statement about the design and therefore a
  ``Finding`` — which is why ``--include``/``--exclude`` are gone too, a
  hand-narrowed packet verifying against a slice nobody designed;
- assembly is deterministic from design plus milestone, which is the premise
  under regenerating a packet rather than storing one.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from absicht.findings import Severity
from absicht.load import load_store
from absicht.models.design import (
    FORMAT_VERSION,
    Behavior,
    Component,
    ComponentLevel,
    Design,
    Lifecycle,
    Milestone,
    Note,
    Observation,
    Rejection,
)
from absicht.models.packet import Fidelity, Packet
from absicht.packet import PacketError, assemble, summarise
from absicht.resolve import Index, resolve

FIXTURES = Path(__file__).parent / "fixtures" / "systems"


def _design(name: str) -> Design:
    return resolve(load_store(FIXTURES / name))


def _fidelities(packet: Packet) -> dict[str, Fidelity]:
    return {element.ref: element.fidelity for element in packet.elements}


# ------------------------------------------------------------- the selection


def test_horizon_one_is_the_slice_whole_and_one_ring_of_contracts() -> None:
    """``clean/``'s milestone read end to end. Whole: the milestone, its two
    scope components, the behavior it includes and the two obligations it
    names. Contract: one ring out in both directions — ``library:pydantic``,
    which ``component:orders`` points at, and ``data:order``, which points
    back at it, because an agent changing a component needs what it calls and
    what calls it alike."""

    packet = assemble(_design("clean"), "milestone:m1")

    assert _fidelities(packet) == {
        "milestone:m1": Fidelity.FULL,
        "component:orders": Fidelity.FULL,
        "component:cancellation": Fidelity.FULL,
        "behavior:order-cancelled": Fidelity.FULL,
        "decision:event-log": Fidelity.FULL,
        "quality:cancel-latency": Fidelity.FULL,
        "component:acme": Fidelity.CONTRACT,
        "constraint:gdpr-erasure": Fidelity.CONTRACT,
        "data:order": Fidelity.CONTRACT,
        "interface:order-events": Fidelity.CONTRACT,
        "library:pydantic": Fidelity.CONTRACT,
        "req:cancel-orders": Fidelity.CONTRACT,
        "resource:order-cache": Fidelity.CONTRACT,
        "resource:order-stream": Fidelity.CONTRACT,
    }
    assert packet.format_version == FORMAT_VERSION
    assert packet.milestone == "milestone:m1"
    assert packet.design == "design:acme"
    assert packet.outcome == "A customer can cancel an order that has not shipped."


def test_horizon_zero_is_the_slice_and_nothing_around_it() -> None:
    """No ring at all leaves exactly what the milestone itself named — which
    is what ``ab features`` assembles with, since it wants the behaviors and
    not the context around them."""

    packet = assemble(_design("clean"), "milestone:m1", horizon=0)

    assert set(_fidelities(packet).values()) == {Fidelity.FULL}
    assert set(_fidelities(packet)) == {
        "milestone:m1",
        "component:orders",
        "component:cancellation",
        "behavior:order-cancelled",
        "decision:event-log",
        "quality:cancel-latency",
    }


def test_horizon_two_adds_the_second_ring_still_at_contract() -> None:
    """A wider horizon widens the contract half only: what was whole stays
    whole, and the elements a second hop reaches are context to respect, never
    something to implement."""

    packet = assemble(_design("clean"), "milestone:m1", horizon=2)

    fidelities = _fidelities(packet)
    assert fidelities["behavior:order-cancelled"] is Fidelity.FULL
    # Two hops out: the goal behind the requirement, the actor who asks for
    # it, and the sibling container under the same system.
    assert fidelities["goal:cheap-orders"] is Fidelity.CONTRACT
    assert fidelities["actor:customer"] is Fidelity.CONTRACT
    assert fidelities["component:catalog"] is Fidelity.CONTRACT
    assert set(_fidelities(assemble(_design("clean"), "milestone:m1"))) < set(fidelities)


def test_elements_arrive_whole_first_and_ref_ordered_within_each_fidelity() -> None:
    """Assembly imposes its own order rather than inheriting the store's, so
    a file rename cannot move a packet's bytes: the whole half first — an
    agent reads what it may change before what it may not — each half sorted
    by ref."""

    packet = assemble(_design("clean"), "milestone:m1")

    refs = [element.ref for element in packet.elements]
    whole = [e.ref for e in packet.elements if e.fidelity is Fidelity.FULL]
    contract = [e.ref for e in packet.elements if e.fidelity is Fidelity.CONTRACT]
    assert refs == whole + contract
    assert whole == sorted(whole)
    assert contract == sorted(contract)


def test_full_fidelity_carries_the_element_exactly_as_built() -> None:
    """Nothing is trimmed on the side the agent may change: the carried dump
    is the model's own, field for field."""

    index = Index(_design("clean"))
    packet = assemble(index.design, "milestone:m1")

    by_ref = {element.ref: element.element for element in packet.elements}
    for ref in ("component:cancellation", "milestone:m1", "behavior:order-cancelled"):
        assert by_ref[ref] == index.local[ref].model_dump(mode="json")


def test_contract_fidelity_drops_only_what_is_behind_the_surface() -> None:
    """``implemented_by`` is the one typed field that reaches past what a
    neighbour publishes, so it is the one field a contract loses — on every
    kind that has one. What stays is the reason to know the neighbour exists:
    a component's responsibility and its place in the nesting, an interface's
    operations and how it fails."""

    packet = assemble(_design("clean"), "milestone:m1")

    by_ref = {element.ref: element.element for element in packet.elements}
    component, interface = by_ref["component:acme"], by_ref["interface:order-events"]
    assert "implemented_by" not in component
    assert "implemented_by" not in interface
    assert component["responsibility"] == "The whole of what we design."
    assert component["level"] == "system"
    assert interface["operations"]
    assert interface["failure_modes"]
    assert interface["declared_by"] == "component:orders"
    # `source` survives both fidelities: a packet stays traceable to the store
    # it was assembled from, whichever side of the cut an element landed on.
    assert component["source"] == "components/acme.md"
    assert by_ref["component:orders"]["source"] == "components/orders.md"


def test_the_milestones_own_lists_ride_verbatim() -> None:
    """The envelope an agent works inside is the milestone's, unedited: what
    must hold, where it is free, what stays open on purpose, and what says the
    slice is finished. Assembly selects elements; it does not re-derive the
    author's obligations."""

    milestone = next(m for m in _design("clean").milestones if m.id == "milestone:m1")

    packet = assemble(_design("clean"), "milestone:m1")

    assert (
        packet.must_hold == milestone.must_hold == ("decision:event-log", "quality:cancel-latency")
    )
    assert packet.may_decide == milestone.may_decide
    assert packet.unresolved == milestone.unresolved == ()
    assert packet.done_when == milestone.done_when == ("behavior:order-cancelled#obs-1",)


def test_every_rejection_the_design_carries_rides_along() -> None:
    """Rejections are not filtered by scope: a dead idea is dead everywhere,
    and an agent re-proposing one costs a review cycle whichever slice it is
    working."""

    design = Design(
        id="design:rejected",
        title="Rejected",
        version="0.1.0",
        components=(_component("component:core"),),
        rejections=(
            Rejection(id="rejection:polling", title="Poll the table"),
            Rejection(id="rejection:shared-db", title="Share the database"),
        ),
        milestones=(Milestone(id="milestone:m", title="M", scope=("component:core",)),),
    )

    packet = assemble(design, "milestone:m")

    assert packet.rejections == ("rejection:polling", "rejection:shared-db")
    assert _fidelities(packet)["rejection:polling"] is Fidelity.FULL


def test_the_design_rev_is_recorded_as_the_caller_spelled_it() -> None:
    """What makes a packet verifiable offline: the commit it was assembled
    from travels with it, so a verification can rebuild the same design
    without the store."""

    packet = assemble(_design("clean"), "milestone:m1", design_rev="c0ffee")

    assert packet.design_rev == "c0ffee"
    assert assemble(_design("clean"), "milestone:m1").design_rev == ""


# --------------------------------------------------------------- behaviors


def _component(ref: str) -> Component:
    return Component(
        id=ref, title=ref.removeprefix("component:").title(), level=ComponentLevel.CONTAINER
    )


def _behavior(
    ref: str, *, at: tuple[str, ...], lifecycle: Lifecycle = Lifecycle.ACTIVE
) -> Behavior:
    """One behavior with a ``must`` observation per ``at`` ref, numbered in the
    order given — enough shape for the selection rules, which read only what a
    behavior watches and whether it is still how the system works."""
    return Behavior(
        id=ref,
        title=ref.removeprefix("behavior:"),
        trigger=f"{ref.removeprefix('behavior:')} happens.",
        lifecycle=lifecycle,
        observations=tuple(
            Observation(id=f"{ref}#obs-{position}", statement=f"observes {target}", at=target)
            for position, target in enumerate(at, start=1)
        ),
    )


def _selection_design() -> Design:
    """One behavior on each side of every selection rule: the work the
    milestone names, an active guard watching the scope, an active behavior
    watching only elsewhere, and a superseded one watching the scope *and*
    composed by the work — so neither route can smuggle it back in."""
    core, elsewhere = "component:core", "component:elsewhere"
    return Design(
        id="design:selection",
        title="Selection",
        version="0.1.0",
        components=(_component(core), _component(elsewhere)),
        behaviors=(
            _behavior("behavior:guard", at=(core,)),
            _behavior("behavior:far", at=(elsewhere,)),
            _behavior("behavior:old", at=(core,), lifecycle=Lifecycle.SUPERSEDED),
            _behavior("behavior:new-work", at=(core, "behavior:old")),
        ),
        milestones=(
            Milestone(id="milestone:m", title="M", includes=("behavior:new-work",), scope=(core,)),
        ),
    )


def test_satisfy_is_the_milestones_includes_and_must_not_break_is_the_rest() -> None:
    """The two behavior lists, read off one design. ``guard`` watches the
    scope and is not the work, so breaking it is a regression; ``far`` watches
    nothing the slice may touch and is none of its business; ``new-work`` is
    the work itself and is never repeated as a standing expectation."""

    packet = assemble(_selection_design(), "milestone:m")

    assert packet.satisfy == ("behavior:new-work",)
    assert packet.must_not_break == ("behavior:guard",)


def test_both_behavior_lists_arrive_whole() -> None:
    """Observations are the actionable part of either list: the work has to be
    built to them, and an expectation that may not break is only checkable
    verbatim."""

    packet = assemble(_selection_design(), "milestone:m")

    fidelities = _fidelities(packet)
    assert fidelities["behavior:new-work"] is Fidelity.FULL
    assert fidelities["behavior:guard"] is Fidelity.FULL


def test_a_superseded_behavior_joins_nothing() -> None:
    """It stopped being how the system works, so handing it to an agent asks
    for the past to be rebuilt. ``behavior:old`` watches the scope and is
    composed by the work — the two routes in — and arrives by neither, at
    neither fidelity."""

    packet = assemble(_selection_design(), "milestone:m")

    assert "behavior:old" not in packet.satisfy
    assert "behavior:old" not in packet.must_not_break
    assert "behavior:old" not in _fidelities(packet)


def test_the_clean_fixtures_superseded_behavior_is_absent_too() -> None:
    """The same rule against a store an author wrote rather than a test:
    ``behavior:order-placed`` observes ``component:orders``, which
    ``milestone:m1`` puts in scope, and is superseded by ``-v2``."""

    packet = assemble(_design("clean"), "milestone:m1")

    assert "behavior:order-placed" not in _fidelities(packet)
    assert packet.must_not_break == ()


def _chain_design() -> Design:
    """A → B → C: the milestone selects A, A composes B, B composes C, and C
    watches nothing in scope."""
    return Design(
        id="design:chain",
        title="Chain",
        version="0.1.0",
        components=(_component("component:core"), _component("component:away")),
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
    """B is the work too, although it watches nothing in scope: one hop from
    what the milestone named is reason enough. C, two hops out, is not the
    work — it arrives as the contract B's observation points at, which is how
    "referenced, not expanded" survives serialization."""

    packet = assemble(_chain_design(), "milestone:m")

    assert packet.satisfy == ("behavior:a", "behavior:b")
    fidelities = _fidelities(packet)
    assert fidelities["behavior:a"] is fidelities["behavior:b"] is Fidelity.FULL
    assert fidelities["behavior:c"] is Fidelity.CONTRACT
    carried = next(e for e in packet.elements if e.ref == "behavior:b")
    assert [o["at"] for o in carried.element["observations"]] == ["behavior:c"]


def test_a_composition_cycle_terminates_instead_of_hanging() -> None:
    """Assembly walks input ``ab check`` has not necessarily graded yet, so a
    cycle it would report as a finding must not hang it. One hop is the whole
    walk: X composing Y and Y composing X cannot re-enter it."""

    design = Design(
        id="design:cycle",
        title="Cycle",
        version="0.1.0",
        components=(_component("component:core"),),
        behaviors=(
            _behavior("behavior:x", at=("component:core", "behavior:y")),
            _behavior("behavior:y", at=("behavior:x",)),
        ),
        milestones=(
            Milestone(
                id="milestone:m", title="M", includes=("behavior:x",), scope=("component:core",)
            ),
        ),
    )

    packet = assemble(design, "milestone:m")

    assert packet.satisfy == ("behavior:x", "behavior:y")
    assert packet.must_not_break == ()


def test_an_include_that_names_nothing_joins_nothing_and_stops_nothing() -> None:
    """``includes`` naming a behavior nothing defines is ``ab check``'s
    dangling-ref finding, not a reason to refuse a packet: no element appears
    for it, no list claims it, and the behaviors named after it still
    expand."""

    design = Design(
        id="design:dangling",
        title="Dangling",
        version="0.1.0",
        components=(_component("component:core"),),
        behaviors=(
            _behavior("behavior:a", at=("component:core", "behavior:b")),
            _behavior("behavior:b", at=("component:core",)),
        ),
        milestones=(
            Milestone(
                id="milestone:m",
                title="M",
                includes=("behavior:ghost", "behavior:a"),
                scope=("component:core",),
            ),
        ),
    )

    packet = assemble(design, "milestone:m")

    assert packet.satisfy == ("behavior:a", "behavior:b")
    assert "behavior:ghost" not in _fidelities(packet)


# ------------------------------------------------------------- the refusals


@pytest.mark.parametrize("ref", ["milestone:nope", "component:orders"])
def test_a_ref_that_names_no_milestone_is_a_lookup_error(ref: str) -> None:
    """A broken invocation, not a statement about the design: an id nothing
    defines and an id that defines something else fail the same way, because
    in both cases nobody named a slice."""

    with pytest.raises(LookupError, match=rf"{ref} is not a milestone of design:acme"):
        assemble(_design("clean"), ref)


def test_a_milestone_that_names_no_scope_is_a_finding() -> None:
    """The milestone exists and says nothing about what may be touched — a
    true statement about the design, so it carries a ``Finding`` rather than a
    usage error. Read off ``broken/``, so the finding can name the file a
    human goes to."""

    with pytest.raises(PacketError) as excinfo:
        assemble(_design("broken"), "milestone:unscoped")

    report = excinfo.value.report
    assert report.rule_id == "packet/empty-scope"
    assert report.severity is Severity.ERROR
    assert report.ref == "milestone:unscoped"
    assert report.source == "milestones/unscoped.md"
    # The exception's own message is the finding's: the CLI echoes `str(error)`
    # to stderr, and that has to be the sentence worth reading.
    assert str(excinfo.value) == report.message


# --------------------------------------------------- more than one repository


def test_a_packet_spans_every_repository_the_slice_lives_in() -> None:
    """``composite/``: one design over two repositories, and the packet is one
    brief. The two containers are implemented in different repositories and
    both arrive whole, with the interface declared on one side and called from
    the other as the contract between them."""

    packet = assemble(_design("composite"), "milestone:invoicing")

    fidelities = _fidelities(packet)
    assert fidelities["component:orders-api"] is Fidelity.FULL
    assert fidelities["component:billing-worker"] is Fidelity.FULL
    assert fidelities["interface:invoice-events"] is Fidelity.CONTRACT
    by_ref = {element.ref: element.element for element in packet.elements}
    assert by_ref["component:orders-api"]["implemented_by"] == ["orders#api"]
    assert by_ref["component:billing-worker"]["implemented_by"] == ["billing#worker"]
    assert packet.done_when == ("behavior:order-settles#obs-2",)


# ------------------------------------------------------------- the artifact


def test_a_note_reaches_no_packet() -> None:
    """An agent never sees a note. A note is not an element, so assembly
    cannot reach one — pinned against a design carrying a note pointed
    straight at the scope."""

    design = Design(
        id="design:noted",
        title="Noted",
        version="0.1.0",
        components=(_component("component:core"),),
        milestones=(Milestone(id="milestone:m", title="M", scope=("component:core",)),),
        notes=(
            Note(
                id="note:k1j2k3",
                created_on=date(2026, 8, 16),
                text="The packet must never carry this.",
                about=("component:core",),
            ),
        ),
    )

    packet = assemble(design, "milestone:m")

    assert "note:" not in packet.model_dump_json()


def test_the_same_design_and_milestone_assemble_identically() -> None:
    """The premise under regenerating a packet instead of storing one: the
    artifact is a function of the design and the milestone, so two assemblies
    of one design agree byte for byte, lists included."""

    design = _selection_design()

    assert (
        assemble(design, "milestone:m").model_dump_json()
        == assemble(design, "milestone:m").model_dump_json()
    )


def test_summarise_is_one_line_per_element_naming_its_fidelity() -> None:
    """The human-readable index of a packet, for somebody diffing two of them:
    every element, once, with the side of the cut it landed on."""

    packet = assemble(_design("clean"), "milestone:m1")

    lines = list(summarise(packet))

    assert len(lines) == len(packet.elements)
    assert lines[0] == "full     behavior:order-cancelled"
    assert "contract library:pydantic" in lines
