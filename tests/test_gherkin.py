"""``absicht.gherkin``: behavioural criteria as Gherkin, nothing else.

The command contracts — flags, exit codes, the bytes on stdout — belong to
``32-packet-cli.md`` and ``33-features.md`` and are not this module's. What
is pinned here is the rendering contract both of them build on, per
``docs/tasks/30-gherkin.md``:

- one ``Scenario:`` per *behavioural* criterion, in the order given
  (acceptance order is criterion-id order), while structural and measured
  criteria are skipped whole — they are ``ab verify``'s and the benchmark's
  concern, not Gherkin's;
- the output is byte-identical across calls: ``ab features --check`` diffs
  against it and ``ab packet --seal``'s digest seals it, so the same input
  spelling different bytes would break both silently;
- ``scenario_digest`` folds each file's *name* into the hash with its
  content — an edited ``then`` and a renamed file are both drift — and is
  independent of dict order, not of the sorted set of files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from absicht.gherkin import render_feature, scenario_digest
from absicht.load import load_store
from absicht.models import Story
from absicht.resolve import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "systems"


@pytest.fixture
def cancel_order() -> Story:
    """The ``clean/`` story the spec's tests are spelled against: two
    behavioural criteria (one with a ``given``) and one structural."""
    design = resolve(load_store(FIXTURES / "clean"))
    return next(story for story in design.stories if story.id == "story:cancel-order")


def test_only_behavioural_criteria_become_scenarios(cancel_order: Story) -> None:
    """Two behavioural plus one structural criterion — the fixture's exact
    split — renders exactly two scenarios; the structural one's statement is
    not Gherkin's to spell."""
    feature = render_feature(cancel_order, cancel_order.acceptance)

    assert feature.count("Scenario:") == 2
    assert "Scenario: story:cancel-order#ac-1" in feature
    assert "Scenario: story:cancel-order#ac-2" in feature
    assert "ac-3" not in feature
    assert "cancellation only consumes" not in feature


def test_steps_come_from_the_criterion_own_fields(cancel_order: Story) -> None:
    """``Given``/``When``/``Then`` lines are the criterion's own fields, with
    ``And`` continuing a section: the fixture's ``#ac-1`` has no ``given``
    and two ``then``s, ``#ac-2`` one of each."""
    feature = render_feature(cancel_order, cancel_order.acceptance)

    lines = feature.splitlines()
    assert "    When the customer cancels a refundable order" in lines
    assert "    Then the order is cancelled" in lines
    assert "    And the refund starts" in lines
    assert "    Given an order that has already shipped" in lines
    assert "    Then cancellation is refused" in lines


def test_the_story_maps_onto_the_gherkin_narrative(cancel_order: Story) -> None:
    """The story's ``actor``/``outcome`` carry the As a/So that framing; the
    title is the want, flattened into ``I want to`` the way story titles
    (imperatives) read as Gherkin infinitives."""
    feature = render_feature(cancel_order, cancel_order.acceptance)

    lines = feature.splitlines()
    assert lines[0] == "Feature: Cancel an order"
    assert "  As a customer" in lines
    assert "  I want to cancel an order" in lines
    assert "  So that the order is cancelled and the refund starts" in lines


def test_a_story_without_actor_or_outcome_omits_those_lines() -> None:
    """The narrative maps the fields a story actually carries: no actor means
    no ``As a`` line, not an empty one — and a story with no behavioural
    criteria still renders, as a bare feature header."""
    story = Story(id="story:bare", title="Ship it")

    feature = render_feature(story, ())

    assert feature.splitlines()[0] == "Feature: Ship it"
    assert "As a" not in feature
    assert "So that" not in feature
    assert "Scenario:" not in feature


def test_rendering_is_byte_identical_across_calls(cancel_order: Story) -> None:
    feature = render_feature(cancel_order, cancel_order.acceptance)

    assert render_feature(cancel_order, cancel_order.acceptance) == feature


def test_the_rendered_feature_is_pinned_whole(
    cancel_order: Story, snapshot: SnapshotAssertion
) -> None:
    """The whole file, byte for byte, for the fixture story: a future
    formatting change has to arrive as a reviewable snapshot update, not as
    silent drift in every ``--check`` and every seal computed afterwards."""
    assert render_feature(cancel_order, cancel_order.acceptance) == snapshot


# --- the scenario digest -------------------------------------------------------


def test_the_digest_moves_when_a_then_line_changes(cancel_order: Story) -> None:
    """The seal's whole point: an edited step is drift. A reworded ``then``
    re-renders to different bytes, and the digest of the re-rendered files
    must say so — this is how ``ab verify`` catches a hand-edited ``.feature``."""
    reworded = cancel_order.acceptance[0].model_copy(
        update={"then": ("the order is cancelled", "the refund is skipped")}
    )
    before = {"cancel-order.feature": render_feature(cancel_order, cancel_order.acceptance)}
    after = {
        "cancel-order.feature": render_feature(
            cancel_order, (reworded, *cancel_order.acceptance[1:])
        )
    }

    assert scenario_digest(after) != scenario_digest(before)


def test_the_digest_stays_put_when_nothing_changed(cancel_order: Story) -> None:
    features = {"cancel-order.feature": render_feature(cancel_order, cancel_order.acceptance)}

    # Same files, different dict insertion order: the digest walks the files
    # sorted by name, so dict order cannot move what the seal records.
    assert scenario_digest(dict(reversed(list(features.items())))) == scenario_digest(features)


def test_the_digest_counts_a_rename_as_a_change() -> None:
    """The filename is part of the hash input, tested directly: identical
    content under a new name is drift too, because the step definitions'
    home moved."""
    same = "Feature: Cancel an order\n"

    assert scenario_digest({"renamed.feature": same}) != scenario_digest(
        {"cancel-order.feature": same}
    )
