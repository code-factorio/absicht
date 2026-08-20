"""``absicht.models.design``: the shapes a record is refused for having.

Rule 3 of the model's own docstring draws the line these tests hold. A
validator there rejects a shape the record cannot have, and everything a
lookup could answer — does this ref resolve, is this requirement realized —
is a report line in ``check`` instead. So what is pinned here is exactly the
set of refusals that happen when a record is built, which is the moment an
author finds out rather than three commands later:

- identity is a typed ``kind:slug`` string, so a ref names its own kind and
  is checkable without a lookup;
- ``Resource.technology`` is free text forever (C4's refusal of a storage
  taxonomy, held at the model): required and non-empty, never enumerated, so
  nothing needs migrating when next year's store arrives;
- a ``must_not`` observation carries no ``timing``: "at no point" and "when"
  cannot both be said, and prose would have let them;
- a behavior anchors its own observations, while zero observations stays
  constructible — a behavior mid-authoring is legitimate on disk, and
  ``policy/behavior-unobserved`` is a report line, not an exception;
- effective timing is computed, never stored: an authored value wins, a
  ``stream`` is eventual, everything else immediate — the one answer both
  ``packet`` and ``verify`` read;
- a ``Design`` offers contracts and nothing else, and holds one element per
  id. Both are only decidable once every file sits in one record, which is
  why ``resolve`` revalidates instead of copying fields across;
- a ``Note`` is a ``Record`` and not an ``Element``: nothing beyond an id and
  a date can be asked of it, because capture friction is what stops a note
  being written at all.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from pydantic import ValidationError

from absicht.models.design import (
    FORMAT_VERSION,
    Assumption,
    Behavior,
    Component,
    ComponentLevel,
    Confidence,
    DataEntity,
    Design,
    Element,
    ExternalService,
    FieldSpec,
    Lifecycle,
    Note,
    Observation,
    Outcome,
    Record,
    Relationship,
    RelationshipType,
    Resource,
    ResourceKind,
    State,
    Term,
    Timing,
)

_ANCHOR = "behavior:new-chat-session"


# ----------------------------------------------------------------- identity


@pytest.mark.parametrize(
    "ref",
    ["order", "Term:order", "term:", "term:-order", "term:Order", "term:order#1"],
)
def test_an_id_that_is_not_a_typed_ref_is_invalid(ref: str) -> None:
    """`kind:slug`, lowercase, no anchor: a ref names its own kind, so a
    checker knows what it points at without resolving it and an element can
    move between files without breaking a link."""

    with pytest.raises(ValidationError, match="id"):
        Term(id=ref, title="Order", definition="A request to buy.")


def test_an_element_says_nothing_until_somebody_says_it() -> None:
    """The defaults are the model's fourth rule made concrete: an element
    nobody finished must not read as "implement as written", and an agent
    must not read confidence into a field nobody filled in."""

    term = Term(id="term:order", title="Order", definition="A request to buy.")

    assert term.state is State.UNKNOWN
    assert term.confidence is Confidence.ASSUMED
    assert term.lifecycle is Lifecycle.ACTIVE
    assert term.reversibility is None


def test_a_record_is_frozen_and_refuses_a_key_it_does_not_know() -> None:
    """`codec` hands pydantic a file's front matter whole. Without
    `extra="forbid"` a misspelled key would be dropped in silence instead of
    reported, and `store/validation` would have nothing to grade."""

    term = Term(id="term:order", title="Order", definition="A request to buy.")

    with pytest.raises(ValidationError, match="definitoin"):
        Term(id="term:order", title="Order", definition="A request.", definitoin="typo")
    with pytest.raises(ValidationError, match="frozen"):
        term.title = "Renamed"


# ----------------------------------------------------------------- resource


@pytest.mark.parametrize(
    "technology",
    ["Redis", "Kafka", "a filesystem path", "PostgreSQL 16"],
)
def test_technology_accepts_any_nonempty_string(technology: str) -> None:
    """C4's refusal of a storage taxonomy, held at the model: `technology` is
    a string, so nothing needs migrating when next year's store arrives."""

    assert _resource(technology).technology == technology


def test_a_resource_without_technology_is_invalid() -> None:
    with pytest.raises(ValidationError, match="technology"):
        Resource(id="resource:cache", title="Cache", resource_kind=ResourceKind.STORE)


@pytest.mark.parametrize("technology", ["", "   "])
def test_an_empty_technology_is_invalid(technology: str) -> None:
    """Whitespace-only prose is no technology — the record strips before it
    validates, so an author who typed nothing gets told, not saved."""

    with pytest.raises(ValidationError, match="technology"):
        _resource(technology)


# -------------------------------------------------------------- observation


@pytest.mark.parametrize("timing", [Timing.IMMEDIATE, Timing.EVENTUAL])
def test_a_must_not_observation_carries_no_timing(timing: Timing) -> None:
    """`must_not` means "at no point"; a timing on it says when the never
    happens, which is not a design anyone meant to record."""

    with pytest.raises(ValidationError, match="must_not"):
        Observation(
            id=f"{_ANCHOR}#obs-1",
            statement="No entry is written to the audit log",
            at="resource:audit-log",
            outcome=Outcome.MUST_NOT,
            timing=timing,
        )


@pytest.mark.parametrize("outcome", [Outcome.MUST, Outcome.SHOULD])
@pytest.mark.parametrize("timing", [None, Timing.IMMEDIATE, Timing.EVENTUAL])
def test_must_and_should_accept_timing_absent_or_present(
    outcome: Outcome, timing: Timing | None
) -> None:
    """Only the negative polarity forbids a timing: positive observations
    name when they become true, or leave it to the default."""

    observation = _observation(outcome=outcome, timing=timing)

    assert observation.timing == timing


@pytest.mark.parametrize("observation_id", ["behavior:x#obs", "behavior:x#obs-", "behavior:x"])
def test_an_observation_id_must_carry_its_ordinal(observation_id: str) -> None:
    """A test binds to this id, so it has to survive every rewording — which
    it only does while the anchor and the ordinal are both part of the id."""

    with pytest.raises(ValidationError, match="id"):
        Observation(id=observation_id, statement="It lands", at="component:one")


# ----------------------------------------------------------------- behavior


def test_a_behavior_rejects_an_observation_anchored_elsewhere() -> None:
    """The id says which behavior owns an observation, so one naming another
    behavior is a broken file rather than a design judgement."""

    with pytest.raises(ValidationError, match="not anchored to 'behavior:new-chat-session'"):
        Behavior(
            id=_ANCHOR,
            title="New chat session",
            trigger="A user starts a new chat session.",
            observations=(_observation(anchor="behavior:other"),),
        )


def test_a_behavior_mid_authoring_needs_no_observations() -> None:
    """Zero observations is loadable: the store must hold work in progress,
    and the emptiness is `policy/behavior-unobserved`'s to report."""

    behavior = Behavior(id=_ANCHOR, title="New chat session", trigger="A user starts one.")

    assert behavior.observations == ()
    assert behavior.lifecycle is Lifecycle.ACTIVE


# ---------------------------------------------------------- effective timing


@pytest.mark.parametrize(
    ("resource_kind", "expected"),
    [
        (ResourceKind.STORE, Timing.IMMEDIATE),
        (ResourceKind.STREAM, Timing.EVENTUAL),
        (None, Timing.IMMEDIATE),
    ],
)
def test_an_unauthored_timing_follows_what_the_observation_points_at(
    resource_kind: ResourceKind | None, expected: Timing
) -> None:
    """Reading a store is checkable now; a message being emitted is asserted
    by consuming it, so it is eventual. A non-resource target — a component,
    an interface, another behavior — has no row in the table and reads
    immediate."""

    assert _observation().effective_timing(resource_kind) is expected


@pytest.mark.parametrize(
    ("authored", "resource_kind"),
    [
        (Timing.IMMEDIATE, ResourceKind.STREAM),
        (Timing.EVENTUAL, ResourceKind.STORE),
    ],
)
def test_an_authored_timing_wins_over_the_default(
    authored: Timing, resource_kind: ResourceKind
) -> None:
    """Both directions against the table: an author who says a stream
    expectation is immediate, or a store one eventual, has said the
    substantive thing and the default must not unsay it."""

    assert _observation(timing=authored).effective_timing(resource_kind) is authored


# -------------------------------------------------------------- relationship


def test_an_edge_from_an_element_to_itself_is_invalid() -> None:
    """Every edge kind is a statement about two elements. A loop of one says
    nothing, and would make each cycle rule report the same non-fact."""

    with pytest.raises(ValidationError, match="points at itself"):
        Relationship(
            source_id="component:orders",
            target_id="component:orders",
            type=RelationshipType.CALLS,
        )


# --------------------------------------------------------------- data entity


def test_identity_naming_a_field_the_entity_does_not_have_is_invalid() -> None:
    """`identity` selects from `fields`, so a name outside them is a typo the
    record itself can catch — no other element has to be consulted."""

    with pytest.raises(ValidationError, match=r"identity names unknown fields: \['ordre'\]"):
        DataEntity(
            id="data:order",
            title="Order",
            fields=(FieldSpec(name="id", type="str"),),
            identity=("ordre",),
        )


# ------------------------------------------------------------------ expiries


_EXPIRING: dict[str, Callable[[date, date], Assumption | ExternalService]] = {
    "assumption": lambda verified, expires: Assumption(
        id="assumption:refunds-settle",
        title="Refunds settle overnight",
        statement="A refund settles within one business day.",
        verified_on=verified,
        expires_on=expires,
    ),
    "external_service": lambda verified, expires: ExternalService(
        id="external:payment-api",
        title="Payment API",
        verified_on=verified,
        expires_on=expires,
    ),
}


@pytest.mark.parametrize("build", _EXPIRING.values(), ids=list(_EXPIRING))
def test_an_expiry_before_the_check_that_set_it_is_invalid(
    build: Callable[[date, date], Assumption | ExternalService],
) -> None:
    """Both records that expire say the same thing: the expiry dates the
    verification, so one falling before it is a transposition rather than a
    record that lapsed the moment it was written."""

    assert build(date(2026, 1, 10), date(2026, 7, 10)).expires_on == date(2026, 7, 10)
    with pytest.raises(ValidationError, match="expires_on is before verified_on"):
        build(date(2026, 7, 10), date(2026, 1, 10))


# ---------------------------------------------------------------------- note


def test_a_note_needs_only_an_id_and_a_creation_date() -> None:
    note = Note(id="note:a1b2c3", created_on=date(2026, 8, 16))

    assert (note.text, note.about, note.done_on, note.promoted_to) == ("", (), None, None)


def test_a_note_without_a_creation_date_is_invalid() -> None:
    with pytest.raises(ValidationError, match="created_on"):
        Note(id="note:a1b2c3")


def test_a_note_is_structurally_not_an_element() -> None:
    """ "Not an element" is a type-system fact here, not a convention: no
    title, state, owner or tags can be asked of a note, so capture friction
    cannot accrete through the model."""

    note = Note(id="note:a1b2c3", created_on=date(2026, 8, 16))

    assert isinstance(note, Record)
    assert not isinstance(note, Element)


# -------------------------------------------------------------------- design


@pytest.mark.parametrize("ref", ["component:orders", "req:cancel-orders", "goal:cheap-orders"])
def test_a_design_exports_contracts_and_nothing_else(ref: str) -> None:
    """A consumer pointing at a requirement depends on our reasoning, and one
    pointing at a component depends on our insides — which is the leakage a
    boundary exists to prevent. Only the contract kinds may cross it."""

    with pytest.raises(ValidationError, match="is not a contract"):
        _design(exports=(ref,))


@pytest.mark.parametrize("ref", ["interface:order-events", "term:order", "data:order"])
def test_the_contract_kinds_may_be_exported(ref: str) -> None:
    assert _design(exports=(ref,)).exports == (ref,)


def test_one_id_names_one_element_across_every_collection() -> None:
    """Uniqueness is a fact about the whole design, not about one directory:
    two files under different kinds can only be caught here, which is why
    `resolve` revalidates instead of copying fields across."""

    duplicate = Component(id="component:orders", title="Orders", level=ComponentLevel.CONTAINER)

    with pytest.raises(ValidationError, match="duplicate id 'component:orders'"):
        _design(components=(duplicate, duplicate))


def test_elements_walks_the_graph_and_leaves_the_notes_out() -> None:
    """`check` starts at `elements()`, so what it yields is what every rule
    can see — in `Design` field order, and never a note: an agent is not
    handed somebody's inbox."""

    design = _design(
        glossary=(Term(id="term:order", title="Order", definition="A request to buy."),),
        components=(
            Component(id="component:orders", title="Orders", level=ComponentLevel.CONTAINER),
        ),
        resources=(_resource("Redis"),),
        notes=(Note(id="note:a1b2c3", created_on=date(2026, 8, 16), about=("component:orders",)),),
    )

    assert [element.id for element in design.elements()] == [
        "term:order",
        "component:orders",
        "resource:cache",
    ]


def test_a_design_survives_a_dump_and_validate_round_trip() -> None:
    """The property `ab build`'s byte-stable output and the codec's front
    matter both rest on: nothing in the record is lost by being written down
    and read back, empty collections included."""

    bare = _design()
    assert (bare.resources, bare.behaviors, bare.relationships) == ((), (), ())
    assert Design.model_validate(bare.model_dump()) == bare

    full = _design(
        resources=(_resource("Redis"),),
        behaviors=(
            Behavior(
                id=_ANCHOR,
                title="New chat session",
                trigger="A user starts a new chat session.",
                observations=(_observation(),),
            ),
        ),
        relationships=(
            Relationship(
                source_id=_ANCHOR,
                target_id="req:chat",
                type=RelationshipType.REALIZES,
            ),
        ),
    )

    assert Design.model_validate(full.model_dump()) == full
    assert full.format_version == FORMAT_VERSION == 1


# ------------------------------------------------------------------ helpers


def _design(**fields: object) -> Design:
    return Design(id="design:tiny", title="Tiny", version="0.1.0", **fields)


def _resource(technology: str) -> Resource:
    return Resource(
        id="resource:cache",
        title="Session cache",
        resource_kind=ResourceKind.STORE,
        technology=technology,
    )


def _observation(
    *,
    anchor: str = _ANCHOR,
    at: str = "resource:cache",
    outcome: Outcome = Outcome.MUST,
    timing: Timing | None = None,
) -> Observation:
    return Observation(
        id=f"{anchor}#obs-1",
        statement="Cache entry exists under sess:{id}",
        at=at,
        outcome=outcome,
        timing=timing,
    )
