"""``absicht.gherkin``: one behavior's observations as Gherkin, nothing else.

The command contracts — flags, exit codes, the bytes on stdout — belong to
``tests/test_features_cli.py`` and ``tests/test_packet_cli.py``. What is
pinned here is the rendering both of them build on:

- one ``.feature`` per behavior and one ``Scenario:`` per observation, in the
  order the behavior states them, each named by the observation id — the id a
  step definition binds to, and the one thing that survives every rewording;
- the mapping is the model's own shape rather than a translation: the trigger
  is the feature description *and* every scenario's ``When``, an observation's
  statement is its ``Then``, and the ``at`` ref rides as a comment so a reader
  knows where to look without leaving the file;
- ``outcome`` and the effective timing ride as tags, because a runner filters
  on tags and on nothing else — and a ``must_not`` carries no timing tag at
  all, since "at no point" has no when to carry;
- the output is byte-identical across calls: ``ab features --check`` diffs
  against it and ``ab packet --seal``'s digest seals it, so the same behavior
  spelling different bytes would break both silently;
- ``observations_digest`` folds each file's *name* into the hash with its
  content — an edited ``Then`` and a renamed file are both drift — and is
  independent of dict insertion order.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from absicht.gherkin import observations_digest, render_feature
from absicht.load import load_store
from absicht.models.design import Behavior, Design, Observation
from absicht.resolve import Index, resolve

FIXTURES = Path(__file__).parent / "fixtures" / "systems"


@pytest.fixture
def clean() -> Index:
    """The ``clean/`` fixture indexed, because the timing tags are resolved
    through what an observation's ``at`` names: the renderer needs the graph,
    not just the behavior."""
    return Index(resolve(load_store(FIXTURES / "clean")))


@pytest.fixture
def order_cancelled(clean: Index) -> Behavior:
    """The behavior every test here is spelled against: three observations,
    one per outcome — a ``must`` on a component, a ``must_not`` on a store and
    a ``should`` on a stream — so one render exercises every tag rule."""
    behavior = clean.get("behavior:order-cancelled")
    assert isinstance(behavior, Behavior)
    return behavior


def _lines(behavior: Behavior, index: Index) -> list[str]:
    return render_feature(behavior, index).splitlines()


def test_the_header_is_the_title_and_the_trigger_is_the_description(
    order_cancelled: Behavior, clean: Index
) -> None:
    """A behavior's own two prose fields, in the two places Gherkin keeps for
    prose. Nothing is invented around them: there is no "as a" and no "so
    that", because a behavior carries neither."""

    lines = _lines(order_cancelled, clean)

    assert lines[0] == "Feature: Cancelling an unshipped order"
    assert lines[1] == ""
    assert lines[2] == "  The customer clicks Cancel on an order that has not shipped."


def test_one_scenario_per_observation_named_by_its_id(
    order_cancelled: Behavior, clean: Index
) -> None:
    """The whole selection rule: every observation becomes a scenario, in the
    behavior's own order, and the scenario's name is the observation id rather
    than its statement — the statement is the part that gets reworded."""

    feature = render_feature(order_cancelled, clean)

    assert feature.count("Scenario:") == len(order_cancelled.observations) == 3
    assert [line for line in feature.splitlines() if line.startswith("  Scenario:")] == [
        "  Scenario: behavior:order-cancelled#obs-1",
        "  Scenario: behavior:order-cancelled#obs-2",
        "  Scenario: behavior:order-cancelled#obs-3",
    ]


def test_every_scenario_replays_the_trigger_and_asserts_one_statement(
    order_cancelled: Behavior, clean: Index
) -> None:
    """One expectation per scenario, under the same ``When`` each time: the
    trigger is what happened, and an observation says one thing about the
    result. A scenario asserting two would fail without saying which."""

    lines = _lines(order_cancelled, clean)

    assert lines.count("    When The customer clicks Cancel on an order that has not shipped.") == 3
    assert "    Then The order reads cancelled." in lines
    assert "    Then No entry for the order remains in the cache." in lines
    assert "    Then An OrderCancelled event carries the reason the customer gave." in lines


def test_each_scenario_names_where_it_is_observed(order_cancelled: Behavior, clean: Index) -> None:
    """The ``at`` ref as a comment: a step definition has to know what it is
    watching, and a comment says so without becoming a step a runner would try
    to bind."""

    lines = _lines(order_cancelled, clean)

    assert "    # at component:orders" in lines
    assert "    # at resource:order-cache" in lines
    assert "    # at resource:order-stream" in lines


def test_the_tags_carry_the_outcome_and_the_effective_timing(
    order_cancelled: Behavior, clean: Index
) -> None:
    """What changes a runner's handling, in the one form a runner can select
    on. The timing is the *effective* one, resolved through what ``at`` names:
    ``#obs-3`` says nothing about when and lands on a stream, so it reads
    ``eventual`` without an author having repeated the default."""

    lines = _lines(order_cancelled, clean)

    assert lines[4] == "  @must @immediate"
    assert lines[16] == "  @should @eventual"


def test_a_must_not_carries_no_timing_tag(order_cancelled: Behavior, clean: Index) -> None:
    """ "At no point" has no when. A timing tag here would let a runner wait
    for the forbidden thing to settle, which is the opposite of the check."""

    lines = _lines(order_cancelled, clean)

    assert lines[10] == "  @must_not"
    assert not any(line.startswith("  @must_not @") for line in lines)


def test_a_behavior_with_no_observations_renders_a_bare_header() -> None:
    """A behavior mid-authoring is legitimate on disk — ``check`` reports it
    through ``policy/behavior-unobserved`` — so the renderer states what there
    is and stops, rather than refusing or inventing a scenario."""

    behavior = Behavior(id="behavior:bare", title="Ship it", trigger="Somebody ships.")
    index = Index(Design(id="design:bare", title="Bare", version="0.1.0", behaviors=(behavior,)))

    assert render_feature(behavior, index) == "Feature: Ship it\n\n  Somebody ships.\n"


def test_an_observation_that_points_at_nothing_still_renders() -> None:
    """A dangling ``at`` is ``check``'s finding, not a rendering failure: the
    scenario is written with the ref it names and the timing that "resolves to
    nothing" implies, so a store somebody is still fixing produces files
    somebody can still read."""

    behavior = Behavior(
        id="behavior:ghost",
        title="Ghost",
        trigger="Something happens.",
        observations=(
            Observation(id="behavior:ghost#obs-1", statement="It lands", at="component:ghost"),
        ),
    )
    index = Index(Design(id="design:ghost", title="Ghost", version="0.1.0", behaviors=(behavior,)))

    lines = _lines(behavior, index)

    assert "  @must @immediate" in lines
    assert "    # at component:ghost" in lines


def test_rendering_is_byte_identical_across_calls(order_cancelled: Behavior, clean: Index) -> None:
    """The premise under ``--check`` and under every seal: the same behavior
    renders the same bytes, so a difference is always drift and never noise."""

    assert render_feature(order_cancelled, clean) == render_feature(order_cancelled, clean)


def test_the_rendered_feature_is_pinned_whole(
    order_cancelled: Behavior, clean: Index, snapshot: SnapshotAssertion
) -> None:
    """The whole file, byte for byte: a future formatting change has to arrive
    as a reviewable snapshot update, not as silent drift in every ``--check``
    and every digest computed afterwards."""

    assert render_feature(order_cancelled, clean) == snapshot


# --- the observations digest ---------------------------------------------------


def test_the_digest_moves_when_a_statement_changes(order_cancelled: Behavior, clean: Index) -> None:
    """The seal's whole point: a reworded observation re-renders to different
    bytes, and the digest must say so — this is how ``ab verify`` catches a
    ``.feature`` file somebody edited by hand."""

    first, *rest = order_cancelled.observations
    reworded = order_cancelled.model_copy(
        update={
            "observations": (
                first.model_copy(update={"statement": "The order reads refunded."}),
                *rest,
            )
        }
    )
    name = "order-cancelled.feature"

    assert observations_digest({name: render_feature(reworded, clean)}) != observations_digest(
        {name: render_feature(order_cancelled, clean)}
    )


def test_the_digest_stays_put_when_nothing_changed(order_cancelled: Behavior, clean: Index) -> None:
    """Same files, different dict insertion order: the walk sorts by filename,
    so the order a caller happened to build the mapping in cannot move what
    the seal recorded."""

    features = {
        "order-cancelled.feature": render_feature(order_cancelled, clean),
        "bare.feature": "Feature: Bare\n",
    }

    assert observations_digest(dict(reversed(list(features.items())))) == observations_digest(
        features
    )


def test_the_digest_counts_a_rename_as_a_change() -> None:
    """The filename is part of the hash input: identical content under a new
    name is drift too, because the step definitions' home moved."""

    same = "Feature: Cancelling an unshipped order\n"

    assert observations_digest({"renamed.feature": same}) != observations_digest(
        {"order-cancelled.feature": same}
    )


def test_the_digest_keeps_a_name_and_its_content_apart() -> None:
    """Name and content fold in with separators between them, so two file sets
    that would concatenate to the same bytes still hash apart — the collision
    a plain ``name + content`` join would let through."""

    assert observations_digest({"a.feature": "bc"}) != observations_digest({"ab.feature": "c"})
