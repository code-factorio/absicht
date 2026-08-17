"""``ab show REF``: one element, resolved, on stdout.

What these tests pin, per ``docs/tasks/21-show.md``:

- both directions of the neighbourhood, each neighbour named with the field
  that carries the ref — the requirement that ``realized_by`` a component, the
  seams a component ``provides``;
- an unknown ref is ``USAGE``: a broken invocation, not a finding about the
  design (``docs/tasks/00-conventions.md``'s exit-code table);
- ``--no-body`` omits the prose in every format — and ``--body`` keeps it, so
  the omission is the flag's doing rather than a renderer that never prints
  bodies at all;
- ``--depth 2`` reaches an outgoing hop ``--depth 1`` does not, while the
  inbound side stays one hop at any depth (the reading of the spec's "how far
  to follow refs" this command implements, also stated in its ``--help``);
- ``--format json`` is the ``schema_version``-enveloped view of
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
from absicht.models import SCHEMA_VERSION

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"

# Unique to `requirement:cancel-orders`' body, so substring assertions about
# the prose cannot be satisfied by a field or a neighbour instead.
PROSE = "may cancel an order while it can still be refunded"


def _show(ref: str, *flags: str) -> Any:
    return runner.invoke(app, ["--store", str(CLEAN), "show", ref, *flags])


def test_inbound_names_the_requirement_that_realizes_the_component() -> None:
    result = _show("component:cancellation")

    assert result.exit_code == ExitCode.OK
    assert "requirement:cancel-orders" in result.stdout
    assert "realized_by" in result.stdout


def test_outbound_names_the_seams_a_component_provides() -> None:
    result = _show("component:orders")

    assert result.exit_code == ExitCode.OK
    assert "seam:order-events" in result.stdout
    assert "provides" in result.stdout


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
    with_body = _show("requirement:cancel-orders", "--format", output_format)
    without_body = _show("requirement:cancel-orders", "--format", output_format, "--no-body")

    assert with_body.exit_code == ExitCode.OK
    assert without_body.exit_code == ExitCode.OK
    assert PROSE in with_body.stdout
    assert PROSE not in without_body.stdout


def test_depth_two_reaches_an_outgoing_hop_depth_one_leaves_out() -> None:
    """`requirement:cancel-orders` → (realized_by) `component:cancellation` →
    (consumes) `seam:order-events`: the second hop exists only at depth 2. The
    inbound side does not grow with depth — expanding it would be the reverse
    trace `ab trace` owns."""

    one = _show("requirement:cancel-orders", "--depth", "1")
    two = _show("requirement:cancel-orders", "--depth", "2")

    assert one.exit_code == ExitCode.OK
    assert two.exit_code == ExitCode.OK
    assert "seam:order-events" not in one.stdout
    assert "seam:order-events" in two.stdout
    # And indented one level deeper than the hop that reached it, which is
    # the distance-from-REF the indentation encodes. A whole-line match: a
    # substring would also pass with the indent drifted deeper.
    assert "    seam:order-events (consumes)" in two.stdout.splitlines()
    assert one.stdout.count("story:cancel-order") == two.stdout.count("story:cancel-order") == 1


def test_an_element_with_no_refs_on_either_side_is_just_itself() -> None:
    """`system:acme` is the root — nothing points at the root, and `externals`
    is empty — so both sections are omitted rather than printed as empty
    headings, and the element still shows with its own fields."""

    result = _show("system:acme")

    assert result.exit_code == ExitCode.OK
    assert "points at:" not in result.stdout
    assert "referenced by:" not in result.stdout
    assert "purpose: Sell things, honestly." in result.stdout


def test_json_envelopes_the_element_and_both_directions() -> None:
    result = _show("component:orders", "--format", "json")

    document = json.loads(result.stdout)

    assert document["schema_version"] == SCHEMA_VERSION
    assert document["element"]["id"] == "component:orders"
    assert document["element"]["source"] == "components/orders.md"
    # Model field order, the order `Index` indexes references in: the same
    # store always spells the same neighbourhood.
    assert [(hop["field"], hop["target"]["id"]) for hop in document["points_at"]] == [
        ("contains", "component:catalog"),
        ("provides", "seam:order-events"),
        ("owns_data", "data:order"),
    ]
    assert [(link["field"], link["source"]["id"]) for link in document["referenced_by"]] == [
        ("provider", "seam:order-events"),
        ("owner_component", "data:order"),
        # The two observations that watch this component, attributed to the
        # behavior that carries them.
        ("at", "behavior:order-placed-v2"),
        ("at", "behavior:order-placed-v2"),
        ("applies_to", "decision:event-log"),
    ]


def test_json_folds_into_a_default_format_only() -> None:
    folded = _show("component:orders", "--json")
    explicit = _show("component:orders", "--format", "text", "--json")

    assert folded.exit_code == ExitCode.OK
    assert json.loads(folded.stdout)["element"]["id"] == "component:orders"
    assert explicit.stdout.startswith("component:orders —")


def test_md_is_a_single_markdown_document() -> None:
    result = _show("requirement:cancel-orders", "--format", "md")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.startswith("# Orders can be cancelled\n")
    assert "- `component:cancellation` — realized_by" in result.stdout
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
    assert 'fields: [{"name": "id", "type": "uuid", "optional": false, "note": ""}' in result.stdout
    assert "identity: id" in result.stdout


# --- behaviors (model addendum) --------------------------------------------------


def test_a_composing_behavior_names_the_behavior_it_composes() -> None:
    """§4.2: `behavior:order-placed-v2` observes `behavior:order-placed` —
    composition, through an observation's `at`, attributed to the behavior
    that carries it — so the composed behavior appears among the refs out,
    named with the field that reached it."""
    result = _show("behavior:order-placed-v2")

    assert result.exit_code == ExitCode.OK
    assert "behavior:order-placed (at)" in result.stdout


def test_observations_render_readably_not_as_a_json_blob() -> None:
    """`show`'s body of a behavior is its observations: one line each with
    the statement, what it points at, the outcome and the timing that
    governs — the effective one, following §1.2's table when the author said
    nothing, and none at all for `must_not`, which carries no timing."""
    result = _show("behavior:order-placed-v2")

    assert result.exit_code == ExitCode.OK
    assert (
        "  behavior:order-placed-v2#obs-1  must, immediate, at resource:order-cache"
        " — The order appears in the order cache"
    ) in result.stdout.splitlines()
    assert (
        "  behavior:order-placed-v2#obs-3  must_not, at resource:order-cache"
        " — No order is cached before payment clears"
    ) in result.stdout.splitlines()
    # obs-5 authored no timing and points at a component: effective immediate.
    assert (
        "  behavior:order-placed-v2#obs-5  should, immediate, at component:orders"
        " — The cache warms before the first read"
    ) in result.stdout.splitlines()
    # The compact JSON blob the field used to render as is gone.
    assert '"statement"' not in result.stdout


def test_json_carries_the_effective_timing_beside_the_authored_one() -> None:
    """The envelope stays additive: `timing` is exactly what the file said
    (null when unsaid), `effective_timing` is the derived answer a consumer
    acts on — and null for `must_not`, which has no when."""
    document = json.loads(_show("behavior:order-placed-v2", "--format", "json").stdout)

    observations = {
        observation["id"]: observation for observation in document["element"]["observations"]
    }

    assert observations["behavior:order-placed-v2#obs-1"]["timing"] == "immediate"
    assert observations["behavior:order-placed-v2#obs-1"]["effective_timing"] == "immediate"
    assert observations["behavior:order-placed-v2#obs-3"]["timing"] is None
    assert observations["behavior:order-placed-v2#obs-3"]["effective_timing"] is None
    assert observations["behavior:order-placed-v2#obs-5"]["timing"] is None
    assert observations["behavior:order-placed-v2#obs-5"]["effective_timing"] == "immediate"
