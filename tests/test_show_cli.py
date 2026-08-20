"""``ab show REF``: one element, resolved, on stdout.

What these tests pin, per ``docs/tasks/21-show.md``:

- both directions of the neighbourhood, each neighbour named with the field
  that carries the ref — the requirement a component ``implements``, the
  interfaces a component ``calls``;
- an unknown ref is ``USAGE``: a broken invocation, not a finding about the
  design (``docs/tasks/00-conventions.md``'s exit-code table);
- ``--no-body`` omits the prose in every format — and ``--body`` keeps it, so
  the omission is the flag's doing rather than a renderer that never prints
  bodies at all;
- ``--depth 2`` reaches an outgoing hop ``--depth 1`` does not, while the
  inbound side stays one hop at any depth (the reading of the spec's "how far
  to follow refs" this command implements, also stated in its ``--help``);
- ``--format json`` is the ``format_version``-enveloped view of
  ``00-conventions.md`` with deterministic neighbour order, and ``--json``
  folds into a default ``--format`` without overriding an explicit one
  (docs/adr/0001);
- ``--format md`` is one Markdown document — the shape the site's element
  pages reuse — and ``--format text`` is snapshotted whole, so a formatting
  change arrives as a reviewable diff, not as a downstream surprise.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.models.design import FORMAT_VERSION

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"

# Unique to `goal:cheap-orders`' body, so substring assertions about the prose
# cannot be satisfied by a field or a neighbour instead.
PROSE = "an order the system failed to explain"


def _show(ref: str, *flags: str) -> Any:
    return runner.invoke(app, ["--store", str(CLEAN), "show", ref, *flags])


def test_inbound_names_the_component_that_implements_the_requirement() -> None:
    result = _show("req:cancel-orders")

    assert result.exit_code == ExitCode.OK
    assert "component:orders" in result.stdout
    assert "implements" in result.stdout


def test_outbound_names_the_interfaces_a_component_calls() -> None:
    result = _show("component:cancellation")

    assert result.exit_code == ExitCode.OK
    assert "interface:order-events" in result.stdout
    assert "calls" in result.stdout


@pytest.mark.parametrize("ref", ["component:ghost", "not-even-a-ref"])
def test_an_unknown_ref_is_a_usage_error(ref: str) -> None:
    """Whatever shape the string has, the answer is the same lookup miss:
    `show` resolves against `Index.by_id` rather than validating the ref's
    syntax, and either way nothing on stdout pretends to be a result."""

    result = _show(ref)

    assert result.exit_code == ExitCode.USAGE
    assert ref in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("output_format", ["text", "json", "md"])
def test_no_body_omits_the_prose_in_every_format(output_format: str) -> None:
    with_body = _show("goal:cheap-orders", "--format", output_format)
    without_body = _show("goal:cheap-orders", "--format", output_format, "--no-body")

    assert with_body.exit_code == ExitCode.OK
    assert without_body.exit_code == ExitCode.OK
    assert PROSE in with_body.stdout
    assert PROSE not in without_body.stdout


def test_depth_two_reaches_an_outgoing_hop_depth_one_leaves_out() -> None:
    """`component:cancellation` → (parent) `component:orders` → (depends_on)
    `resource:order-cache`: the second hop exists only at depth 2. The inbound
    side does not grow with depth — expanding it would be the reverse trace
    `ab trace` owns."""

    one = _show("component:cancellation", "--depth", "1")
    two = _show("component:cancellation", "--depth", "2")

    assert one.exit_code == ExitCode.OK
    assert two.exit_code == ExitCode.OK
    assert "resource:order-cache" not in one.stdout
    assert "resource:order-cache" in two.stdout
    # And indented one level deeper than the hop that reached it, which is
    # the distance-from-REF the indentation encodes. A whole-line match: a
    # substring would also pass with the indent drifted deeper.
    assert "    resource:order-cache (depends_on)" in two.stdout.splitlines()
    assert one.stdout.count("milestone:m1") == two.stdout.count("milestone:m1") == 1


def test_an_element_with_no_refs_on_either_side_is_just_itself() -> None:
    """`term:order` is a definition — it names no element and no element names
    it — so both sections are omitted rather than printed as empty headings,
    and the element still shows with its own fields."""

    result = _show("term:order")

    assert result.exit_code == ExitCode.OK
    assert "points at:" not in result.stdout
    assert "referenced by:" not in result.stdout
    assert (
        "definition: A customer's request to buy one or more items, before it ships."
        in result.stdout
    )


def test_json_envelopes_the_element_and_both_directions() -> None:
    result = _show("component:orders", "--format", "json")

    document = json.loads(result.stdout)

    assert document["format_version"] == FORMAT_VERSION
    assert document["element"]["id"] == "component:orders"
    assert document["element"]["source"] == "components/orders.md"
    # Model field order first, then the file's own `relates` block in the
    # order it spelled its edges: the same store always spells the same
    # neighbourhood.
    assert [(hop["field"], hop["target"]["id"]) for hop in document["points_at"]] == [
        ("parent", "component:acme"),
        ("implements", "req:cancel-orders"),
        ("constrained_by", "constraint:gdpr-erasure"),
        ("depends_on", "library:pydantic"),
        ("depends_on", "resource:order-cache"),
        ("depends_on", "resource:order-stream"),
    ]
    assert [(link["field"], link["source"]["id"]) for link in document["referenced_by"]] == [
        # The observations that watch this component, attributed to the
        # behaviors that carry them.
        ("at", "behavior:order-cancelled"),
        ("at", "behavior:order-placed"),
        ("parent", "component:cancellation"),
        ("declared_by", "interface:order-events"),
        ("owner_component", "data:order"),
        ("applies_to", "decision:event-log"),
        ("scope", "milestone:m1"),
    ]


def test_json_folds_into_a_default_format_only() -> None:
    folded = _show("component:orders", "--json")
    explicit = _show("component:orders", "--format", "text", "--json")

    assert folded.exit_code == ExitCode.OK
    assert json.loads(folded.stdout)["element"]["id"] == "component:orders"
    assert explicit.stdout.startswith("component:orders —")


def test_md_is_a_single_markdown_document() -> None:
    result = _show("goal:cheap-orders", "--format", "md")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.startswith("# Ordering costs less to support\n")
    assert "- `req:cancel-orders` — derives_from" in result.stdout
    assert "## Body" in result.stdout


def test_the_text_format_is_snapshotted(snapshot: SnapshotAssertion) -> None:
    """The golden text view: one component with both directions populated, so
    a change to any line of the rendering shows up as a diff to review."""

    result = _show("component:orders")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == snapshot


def test_a_negative_depth_is_a_usage_error() -> None:
    result = _show("component:orders", "--depth", "-1")

    assert result.exit_code == ExitCode.USAGE
    assert "--depth" in result.stderr


def test_structured_field_values_render_on_one_line() -> None:
    """`data:order`'s `fields` is the clean fixture's one structured value —
    neither a string nor a list of strings. It stays on the field's own line
    as compact JSON rather than being dropped or given a bespoke
    pretty-printer per shape."""

    result = _show("data:order")

    assert result.exit_code == ExitCode.OK
    assert 'fields: [{"name": "id", "type": "str", "optional": false, "note": ""}' in result.stdout
    assert "identity: id" in result.stdout


# --- behaviors (model addendum) --------------------------------------------------


def test_a_composing_behavior_names_the_behavior_it_composes() -> None:
    """§4.2: `behavior:order-placed-v2` observes `behavior:order-placed` —
    composition, through an observation's `at`, attributed to the behavior
    that carries it — so the composed behavior appears among the refs out,
    named with the field that reached it. The mark beside the id is §5's:
    the composed behavior is superseded, and a neighbour line is one of the
    places it must not read as current."""
    result = _show("behavior:order-placed-v2")

    assert result.exit_code == ExitCode.OK
    assert "behavior:order-placed [superseded] (at)" in result.stdout


def test_observations_render_readably_not_as_a_json_blob() -> None:
    """`show`'s body of a behavior is its observations: one line each with
    the statement, what it points at, the outcome and the timing that
    governs — the effective one, following §1.2's table when the author said
    nothing, and none at all for `must_not`, which carries no timing."""
    result = _show("behavior:order-cancelled")

    assert result.exit_code == ExitCode.OK
    assert (
        "  behavior:order-cancelled#obs-1  must, immediate, at component:orders"
        " — The order reads cancelled."
    ) in result.stdout.splitlines()
    assert (
        "  behavior:order-cancelled#obs-2  must_not, at resource:order-cache"
        " — No entry for the order remains in the cache."
    ) in result.stdout.splitlines()
    # obs-3 authored no timing and points at a stream: effective eventual.
    assert (
        "  behavior:order-cancelled#obs-3  should, eventual, at resource:order-stream"
        " — An OrderCancelled event carries the reason the customer gave."
    ) in result.stdout.splitlines()
    # The other half of §1.2's table: nothing authored, pointing at a
    # component — effective immediate.
    browsable = _show("behavior:catalog-browsable")
    assert (
        "  behavior:catalog-browsable#obs-1  must, immediate, at component:catalog"
        " — The catalog answers with the items that are for sale."
    ) in browsable.stdout.splitlines()
    # The compact JSON blob the field used to render as is gone.
    assert '"statement"' not in result.stdout


def test_json_carries_the_effective_timing_beside_the_authored_one() -> None:
    """The envelope stays additive: `timing` is exactly what the file said
    (null when unsaid), `effective_timing` is the derived answer a consumer
    acts on — and null for `must_not`, which has no when."""
    document = json.loads(_show("behavior:order-cancelled", "--format", "json").stdout)

    observations = {
        observation["id"]: observation for observation in document["element"]["observations"]
    }

    assert observations["behavior:order-cancelled#obs-1"]["timing"] == "immediate"
    assert observations["behavior:order-cancelled#obs-1"]["effective_timing"] == "immediate"
    assert observations["behavior:order-cancelled#obs-2"]["timing"] is None
    assert observations["behavior:order-cancelled#obs-2"]["effective_timing"] is None
    assert observations["behavior:order-cancelled#obs-3"]["timing"] is None
    assert observations["behavior:order-cancelled#obs-3"]["effective_timing"] == "eventual"


# --- derived scope, composition, supersession (model addendum §4, §5) ------------


def test_a_behavior_names_its_derived_scope_composition_and_supersession() -> None:
    """`show`'s behavior view carries the three computed facts the addendum
    insists are never stored — §4.1's scope, §4.2's composes/composed_by, §5's
    superseded_by — in a `derived:` block of its own: they are answers about
    the behavior, not fields the file authors."""
    result = _show("behavior:order-placed")

    assert result.exit_code == ExitCode.OK
    # One observation, on one component: the §4.1 classification is `local`.
    assert "scope: local" in result.stdout
    assert "superseded_by: behavior:order-placed-v2" in result.stdout
    # order-placed-v2's obs-1 observes it: the composition reverse edge.
    assert "composed_by: behavior:order-placed-v2" in result.stdout


def test_derived_lines_without_content_are_omitted() -> None:
    """`catalog-browsable` composes nothing, is composed by nothing and
    supersedes nothing: the block says its scope and stays silent about the
    sides that are empty, the same omit-don't-prove-empty discipline the
    `points at:` and `referenced by:` sections hold."""
    result = _show("behavior:catalog-browsable")

    assert result.exit_code == ExitCode.OK
    assert "scope: local" in result.stdout
    assert "composes:" not in result.stdout
    assert "composed_by:" not in result.stdout
    assert "superseded_by:" not in result.stdout


def test_json_carries_the_derived_facts_additive_to_the_element() -> None:
    """The envelope stays additive: the four derived fields ride beside
    `element` — never inside it, where they would read as authored — and a
    non-behavior's envelope carries none of them."""
    behavior = json.loads(_show("behavior:order-placed", "--format", "json").stdout)
    component = json.loads(_show("component:orders", "--format", "json").stdout)

    assert behavior["scope"] == "local"
    assert behavior["superseded_by"] == ["behavior:order-placed-v2"]
    assert behavior["composed_by"] == ["behavior:order-placed-v2"]
    assert behavior["composes"] == []
    assert "scope" not in behavior["element"]
    assert not any(
        key in component for key in ("scope", "composes", "composed_by", "superseded_by")
    )


def test_a_superseded_behavior_is_marked_wherever_it_appears() -> None:
    """§5: a superseded behavior is not deleted, but it must not read as
    current — marked on its own header, on the neighbour lines of the views it
    appears in (here: the replacement that composes it, and the component it
    watches), and in the markdown shape the site's pages reuse. Its `ab list`
    row is pinned in test_list_cli.py."""
    focus = _show("behavior:order-placed")
    composer = _show("behavior:order-placed-v2")
    watched = _show("component:orders")
    page = _show("behavior:order-placed-v2", "--format", "md")

    assert "behavior:order-placed [superseded] — Placing an order (the first cut)" in focus.stdout
    assert "behavior:order-placed [superseded] (at)" in composer.stdout
    assert "behavior:order-placed [superseded] (at)" in watched.stdout
    assert "`behavior:order-placed` [superseded] — at" in page.stdout
    assert "[superseded]" not in _show("behavior:catalog-browsable").stdout
