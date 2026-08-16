"""``absicht.models``: the addendum types — Resource, Behavior, Observation, Note.

Model-layer contracts no store round trip is needed to exercise: these four
shapes are the foundation every later addendum task (store wiring, check
rules, packets, verification) builds on, and each test pins one decision
[docs/tasks/51-model-behaviors-resources.md] leaves to this module:

- ``technology`` is free text forever (addendum §1.1) — required and
  non-empty, but never enumerated, so a storage taxonomy cannot accrete
  where a string was promised;
- a ``must_not`` observation carries no ``timing`` (§3.1): ``must_not``
  means "at no point", which is a shape the record cannot have — the same
  line ``Criterion._shape_matches_kind`` walks, a parse-time failure rather
  than a check finding;
- a behavior anchors its observations the way a story anchors criteria,
  while zero observations stays constructible: a behavior mid-authoring is
  legitimate on disk, and ``policy/behavior-needs-observations`` is a report
  line, not an exception (models.py's own rule 4);
- effective timing is computed, never stored
  ([docs/tasks/50-addendum-conventions.md]): an authored value wins,
  ``stream`` defaults ``eventual``, everything else ``immediate`` — the one
  answer both ``packet`` and ``verify`` will need;
- a note is a ``Record``, not an ``Element``: nothing required beyond an id
  and a creation date, because the capture-friction rule (§6) is a hard
  constraint, not a preference.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from absicht.models import (
    SCHEMA_VERSION,
    Behavior,
    Design,
    Element,
    Lifecycle,
    Note,
    Observation,
    Outcome,
    Resource,
    ResourceKind,
    System,
    Timing,
)

_ANCHOR = "behavior:new-chat-session"


# ---------------------------------------------------------------- resource


@pytest.mark.parametrize(
    "technology",
    ["Redis", "Stripe API", "a filesystem path", "PostgreSQL 16"],
)
def test_technology_accepts_any_nonempty_string(technology: str) -> None:
    """The C4 refusal of a storage taxonomy, held at the model: `technology`
    is a string, so nothing needs migrating when next year's store arrives."""

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


# ------------------------------------------------------------- observation


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


# ---------------------------------------------------------------- behavior


def test_a_behavior_rejects_an_observation_anchored_elsewhere() -> None:
    """Same rule as a criterion on a story: an observation id carries its
    behavior, and a mismatch is a broken file, not a broken design."""

    with pytest.raises(ValidationError, match="not anchored to 'behavior:new-chat-session'"):
        Behavior(
            id=_ANCHOR,
            title="New chat session",
            trigger="A user starts a new chat session.",
            observations=(_observation(anchor="behavior:other"),),
        )


def test_a_behavior_mid_authoring_needs_no_observations() -> None:
    """Zero observations is loadable: the store must hold work in progress,
    and the emptiness is `policy/behavior-needs-observations`'s to report."""

    behavior = Behavior(id=_ANCHOR, title="New chat session", trigger="A user starts one.")

    assert behavior.observations == ()
    assert behavior.lifecycle is Lifecycle.ACTIVE


# --------------------------------------------------------- effective timing


@pytest.mark.parametrize(
    ("resource_kind", "expected"),
    [
        (ResourceKind.STORE, Timing.IMMEDIATE),
        (ResourceKind.ENDPOINT, Timing.IMMEDIATE),
        (ResourceKind.STREAM, Timing.EVENTUAL),
        (None, Timing.IMMEDIATE),
    ],
)
def test_an_unauthored_timing_follows_what_the_observation_points_at(
    resource_kind: ResourceKind | None, expected: Timing
) -> None:
    """The addendum §1.2 default table: reading a store or intercepting a
    call is checkable now, a message being emitted is asserted by consuming
    it — eventual. A non-resource target (component, seam, behavior) has no
    row in the table and defaults immediate."""

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


# -------------------------------------------------------------------- note


def test_a_note_needs_only_an_id_and_a_creation_date() -> None:
    note = Note(id="note:a1b2c3", created=date(2026, 8, 16))

    assert (note.ref, note.promoted_to, note.source, note.body) == (None, None, "", "")


def test_a_note_without_a_creation_date_is_invalid() -> None:
    with pytest.raises(ValidationError, match="created"):
        Note(id="note:a1b2c3")


def test_a_note_is_structurally_not_an_element() -> None:
    """The addendum's "not an element" is a type-system fact, not a
    convention: no title, state, owner or tags can be asked of a note, so
    capture friction cannot accrete through the model."""

    assert not isinstance(Note(id="note:a1b2c3", created=date(2026, 8, 16)), Element)


# ------------------------------------------------------------------ design


def test_design_round_trips_with_the_new_kinds_present_and_absent() -> None:
    """The new collections are additive: an old store builds to the same
    artifact shape, and a design holding the new kinds survives a
    dump/validate round trip — the property `ab build`'s byte-stable output
    and the codec's front matter both rest on."""

    bare = Design(system=System(id="system:tiny", title="Tiny"))
    assert (bare.resources, bare.behaviors) == ((), ())
    assert Design.model_validate(bare.model_dump()) == bare

    full = Design(
        system=System(id="system:tiny", title="Tiny"),
        resources=(_resource("Redis"),),
        behaviors=(
            Behavior(
                id=_ANCHOR,
                title="New chat session",
                trigger="A user starts a new chat session.",
                observations=(
                    _observation(
                        statement="Cache entry exists under sess:{id}", at="resource:cache"
                    ),
                ),
            ),
        ),
    )

    assert Design.model_validate(full.model_dump()) == full
    # Additive fields, no bump: existing stores and their artifacts stay
    # readable, which is what `SCHEMA_VERSION` staying put means.
    assert full.schema_version == SCHEMA_VERSION == 1


# ---------------------------------------------------------------- helpers


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
    statement: str = "Cache entry exists under sess:{id}",
    at: str = "resource:cache",
    outcome: Outcome = Outcome.MUST,
    timing: Timing | None = None,
) -> Observation:
    return Observation(
        id=f"{anchor}#obs-1",
        statement=statement,
        at=at,
        outcome=outcome,
        timing=timing,
    )
