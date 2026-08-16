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
    assert one.stdout.count("story:cancel-order") == two.stdout.count("story:cancel-order") == 1


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
