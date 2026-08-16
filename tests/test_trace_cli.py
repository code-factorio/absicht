"""``ab trace REF``: traceability paths through the ref graph.

What these tests pin, per ``docs/tasks/24-trace.md``:

- the known chain of ``clean/`` — requirement to component to seam to the
  decision that applies to it — comes back as a path with every relation and
  its direction named. The last hop is upward (the decision points at the
  component), which is exactly why the default walk is both directions;
- ``--to`` is point-to-point, not the reachable set filtered: the answer
  holds only paths that end at the target, and between two elements with no
  route between them it is empty and ``OK`` — no path found is information,
  not an error;
- ``--up`` and ``--down`` each restrict the walk to one direction on
  ``requirement:cancel-orders``, whose two sides are asymmetric: everything
  downstream is components, seams and data; upstream is exactly one story
  and one milestone;
- ``--up --down`` together is the default both-direction walk, not an error;
- ``--format json`` is the ``schema_version`` envelope of
  ``00-conventions.md`` (with a ``cycle_hit`` flag spelling whether the walk
  declined a hop that would have repeated an element), ``--json`` folds into
  a default ``--format`` without overriding an explicit one (docs/adr/0001),
  and ``--format mermaid`` is a ``graph TD`` block of refs and relations;
- an unknown REF — or an unknown ``--to`` — is ``USAGE``, the exit-code
  table's broken invocation: an empty answer would read as "no path", which
  is a different claim than "no such element".

The walk's cycle guard — a hop onto an element already on the current path
is declined rather than followed — is pinned on ``broken/``'s contains cycle
in ``tests/test_render.py``: that store cannot reach the CLI, its unreadable
files are ``build``'s refusal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.models import SCHEMA_VERSION

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"

# The last line of a text answer whose walk declined a repeat: the note the
# cycle guard surfaces instead of looping.
CYCLE_NOTE = "note: a cycle was hit; paths stop at the first repeat rather than looping"


def _trace(ref: str, *flags: str) -> Any:
    return runner.invoke(app, ["--store", str(CLEAN), "trace", ref, *flags])


def _document(ref: str, *flags: str) -> dict[str, Any]:
    """The ``--format json`` answer, with exit code and envelope asserted once
    here rather than in every test below."""
    result = _trace(ref, "--format", "json", *flags)
    assert result.exit_code == ExitCode.OK
    document = json.loads(result.stdout)
    assert document["schema_version"] == SCHEMA_VERSION
    return document


def _steps(path: list[dict[str, str]]) -> tuple[tuple[str, str, str], ...]:
    """One path as ``(field, direction, ref)`` hops — the shape every path
    assertion below reads."""
    return tuple((step["field"], step["direction"], step["ref"]) for step in path)


# --- the paths -----------------------------------------------------------------


def test_the_known_chain_comes_back_with_every_relation_and_direction() -> None:
    """The spec's own example chain: a requirement realized by a component
    that consumes a seam provided by the component a decision applies to.
    The store's reciprocal pairs (`consumes`/`consumers`, `provider`/
    `provides`) mean other variants of this chain exist too — this asserts
    the canonical one is among them, spelled exactly."""
    paths = [
        _steps(path)
        for path in _document("requirement:cancel-orders", "--to", "decision:event-log")["paths"]
    ]

    assert (
        ("realized_by", "down", "component:cancellation"),
        ("consumes", "down", "seam:order-events"),
        ("provider", "down", "component:orders"),
        ("applies_to", "up", "decision:event-log"),
    ) in paths


def test_to_answers_only_paths_that_end_at_the_target() -> None:
    """Point-to-point, not the reachable set filtered: nothing here passes
    through the decision (its one ref points the other way), so every answer
    ends at it — and `requirement:browse-catalog`'s side of the graph has no
    route to it at all, which is an empty answer and `OK`."""
    paths = [
        _steps(path)
        for path in _document("requirement:cancel-orders", "--to", "decision:event-log")["paths"]
    ]

    assert paths
    assert all(path[-1] == ("applies_to", "up", "decision:event-log") for path in paths)

    result = _trace("requirement:browse-catalog", "--to", "decision:event-log")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""
    assert _document("requirement:browse-catalog", "--to", "decision:event-log")["paths"] == []


def test_down_follows_only_the_elements_own_refs() -> None:
    """Every simple downward path from the requirement, prefixes included, in
    walk order: the deterministic answer a consumer diffs. `story:cancel-order`
    and `milestone:m1` sit upstream and must not appear; the diamond through
    `data:order` back to `orders` appears as its own routes, cut at the repeat
    rather than followed around again."""
    document = _document("requirement:cancel-orders", "--down")

    assert [_steps(path) for path in document["paths"]] == [
        (("realized_by", "down", "component:cancellation"),),
        (
            ("realized_by", "down", "component:cancellation"),
            ("consumes", "down", "seam:order-events"),
        ),
        (
            ("realized_by", "down", "component:cancellation"),
            ("consumes", "down", "seam:order-events"),
            ("provider", "down", "component:orders"),
        ),
        (
            ("realized_by", "down", "component:cancellation"),
            ("consumes", "down", "seam:order-events"),
            ("provider", "down", "component:orders"),
            ("contains", "down", "component:catalog"),
        ),
        (
            ("realized_by", "down", "component:cancellation"),
            ("consumes", "down", "seam:order-events"),
            ("provider", "down", "component:orders"),
            ("owns_data", "down", "data:order"),
        ),
        (
            ("realized_by", "down", "component:cancellation"),
            ("consumes", "down", "seam:order-events"),
            ("carries", "down", "data:order"),
        ),
        (
            ("realized_by", "down", "component:cancellation"),
            ("consumes", "down", "seam:order-events"),
            ("carries", "down", "data:order"),
            ("owner_component", "down", "component:orders"),
        ),
        (
            ("realized_by", "down", "component:cancellation"),
            ("consumes", "down", "seam:order-events"),
            ("carries", "down", "data:order"),
            ("owner_component", "down", "component:orders"),
            ("contains", "down", "component:catalog"),
        ),
    ]


def test_up_follows_only_refs_pointing_at_the_start() -> None:
    """The upstream side of the same requirement is one story satisfied by it
    and one milestone including that story — a chain with no way back, so
    unlike downstream nothing is declined on the way."""
    document = _document("requirement:cancel-orders", "--up")

    assert [_steps(path) for path in document["paths"]] == [
        (("satisfies", "up", "story:cancel-order"),),
        (
            ("satisfies", "up", "story:cancel-order"),
            ("includes", "up", "milestone:m1"),
        ),
    ]
    assert document["cycle_hit"] is False


def test_up_and_down_together_is_the_default_both_direction_walk() -> None:
    """Both flags at once is redundant, not contradictory: the spec's default
    for neither flag, and byte-identical to it."""
    both = _trace("requirement:cancel-orders", "--up", "--down", "--format", "json")
    default = _trace("requirement:cancel-orders", "--format", "json")

    assert both.exit_code == ExitCode.OK
    assert both.stdout == default.stdout


def test_the_walk_reports_the_hops_it_declined_as_a_cycle_hit() -> None:
    """`orders` provides the seam whose `provider` it is, and `owns_data`/
    `owner_component` cross the same pair in both directions — reciprocal
    pairs the schema invites. The downward walk declines them rather than
    looping and says so: `cycle_hit` is information about the shape of the
    graph, `ab check`'s `integrity/cycle` rule is the judgement about which
    relations may loop."""
    assert _document("requirement:cancel-orders", "--down")["cycle_hit"] is True


# --- the formats -----------------------------------------------------------------


def test_json_envelopes_the_answer() -> None:
    to = _document("requirement:cancel-orders", "--to", "decision:event-log")
    without = _document("requirement:cancel-orders")

    assert to["from"] == "requirement:cancel-orders"
    assert to["to"] == "decision:event-log"
    assert without["to"] is None


def test_json_folds_into_a_default_format_only() -> None:
    folded = _trace("requirement:cancel-orders", "--up", "--json")
    explicit_text = _trace("requirement:cancel-orders", "--up", "--format", "text", "--json")
    explicit_mermaid = _trace("requirement:cancel-orders", "--up", "--format", "mermaid", "--json")

    assert folded.exit_code == ExitCode.OK
    assert json.loads(folded.stdout)["paths"]
    assert explicit_text.stdout.startswith("requirement:cancel-orders <--satisfies--")
    assert explicit_mermaid.stdout.startswith("graph TD")


def test_text_spells_each_path_as_one_line_with_directional_arrows() -> None:
    """A hop reads left to right along the path: `-->` for a ref the left
    element carries, `<--` for a hop against one the right element carries."""
    result = _trace("requirement:cancel-orders", "--to", "decision:event-log")

    assert result.exit_code == ExitCode.OK
    assert (
        "requirement:cancel-orders --realized_by--> component:cancellation"
        " --consumes--> seam:order-events --provider--> component:orders"
        " <--applies_to-- decision:event-log"
    ) in result.stdout.splitlines()


def test_text_notes_the_cycle_hit_and_nothing_else_when_empty() -> None:
    """The note is the last line of a text answer, and only the note prints
    when no path exists — no blank line where a path would be."""
    down = _trace("requirement:cancel-orders", "--down")

    assert down.exit_code == ExitCode.OK
    assert down.stdout.splitlines()[-1] == CYCLE_NOTE

    empty = _trace("requirement:browse-catalog", "--to", "decision:event-log")

    assert empty.exit_code == ExitCode.OK
    assert empty.stdout == ""


def test_mermaid_is_one_graph_td_block_of_refs_and_relations() -> None:
    """Nodes first in first-appearance order, then labelled edges — the same
    emitter `ab render --format mermaid` will call (docs/tasks/27-render-
    diagrams.md), pinned here so the two cannot drift apart. Mermaid node ids
    cannot carry the `:` a ref is spelled with, so the id is the ref with
    colons flattened and the full ref rides along as the label."""
    result = _trace("requirement:cancel-orders", "--up", "--format", "mermaid")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "graph TD",
        '  requirement_cancel_orders["requirement:cancel-orders"]',
        '  story_cancel_order["story:cancel-order"]',
        '  milestone_m1["milestone:m1"]',
        "  requirement_cancel_orders -->|satisfies| story_cancel_order",
        "  story_cancel_order -->|includes| milestone_m1",
    ]


# --- broken invocations ----------------------------------------------------------


def test_an_unknown_start_is_a_usage_error() -> None:
    """`trace` resolves REF against `Index.by_id` rather than validating the
    ref's syntax, so any lookup miss is the same `USAGE` — consistent with
    `show` and `gaps --blocking`."""
    result = _trace("component:ghost")

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""


def test_an_unknown_target_is_a_usage_error() -> None:
    """An empty answer would read as "no path to it", which is a different
    claim than "no such element"."""
    result = _trace("requirement:cancel-orders", "--to", "decision:never-made")

    assert result.exit_code == ExitCode.USAGE
    assert "--to" in result.stderr
    assert result.stdout == ""
