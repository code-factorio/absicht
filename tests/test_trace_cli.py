"""``ab trace REF``: traceability paths through the ref graph.

What these tests pin, per ``docs/tasks/24-trace.md``:

- the known chain of ``clean/`` — a requirement, the component implementing
  it, the interface that component declares, and the decision that applies to
  it — comes back as a path with every relation and its direction named. Most
  of that chain is walked upward (the component points at the requirement
  through ``implements``, the decision at the component through
  ``applies_to``), which is exactly why the default walk is both directions;
- ``--to`` is point-to-point, not the reachable set filtered: the answer
  holds only paths that end at the target, and between two elements with no
  route between them it is empty and ``OK`` — no path found is information,
  not an error;
- ``--up`` and ``--down`` each restrict the walk to one direction on
  ``req:cancel-orders``, whose two sides are asymmetric: downstream is
  exactly the actor it names and the goal it derives from; upstream is
  everything that implements or realizes it, and onward from there the
  components, interfaces, data, decisions and milestones;
- ``--up --down`` together is the default both-direction walk, not an error;
- ``--format json`` is the ``format_version`` envelope of
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
from absicht.models.design import FORMAT_VERSION

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
    assert document["format_version"] == FORMAT_VERSION
    return document


def _steps(path: list[dict[str, str]]) -> tuple[tuple[str, str, str], ...]:
    """One path as ``(field, direction, ref)`` hops — the shape every path
    assertion below reads."""
    return tuple((step["field"], step["direction"], step["ref"]) for step in path)


# --- the paths -----------------------------------------------------------------


def test_the_known_chain_comes_back_with_every_relation_and_direction() -> None:
    """The spec's own example chain: a requirement implemented by a component
    that declares the interface another component calls, ending at the
    decision that applies to it. The store's reciprocal pairs (`satisfies` on
    the component, `scope` on the quality, crossing the same pair both ways)
    mean other variants of this chain exist too — this asserts the canonical
    ones are among them, spelled exactly."""
    paths = [
        _steps(path)
        for path in _document("req:cancel-orders", "--to", "decision:event-log")["paths"]
    ]

    # The short chain: nothing between the requirement and the decision but
    # the component both of them name.
    assert (
        ("implements", "up", "component:orders"),
        ("applies_to", "up", "decision:event-log"),
    ) in paths
    # The chain through the interface, which turns around at the milestone —
    # the one hop here taken with a ref's own arrow rather than against it.
    assert (
        ("implements", "up", "component:orders"),
        ("declared_by", "up", "interface:order-events"),
        ("calls", "up", "component:cancellation"),
        ("scope", "up", "milestone:m1"),
        ("must_hold", "down", "decision:event-log"),
    ) in paths


def test_to_answers_only_paths_that_end_at_the_target() -> None:
    """Point-to-point, not the reachable set filtered: every answer ends at
    the decision — and `term:order` is unreachable from anywhere (the glossary
    term points at nothing and nothing points at it), which is an empty answer
    and `OK`: no path found is information, not an error."""
    paths = [
        _steps(path)
        for path in _document("req:cancel-orders", "--to", "decision:event-log")["paths"]
    ]

    assert paths
    assert all(path[-1][2] == "decision:event-log" for path in paths)

    result = _trace("req:cancel-orders", "--to", "term:order")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""
    assert _document("req:cancel-orders", "--to", "term:order")["paths"] == []


def test_down_follows_only_the_elements_own_refs() -> None:
    """Every simple downward path from the requirement, prefixes included, in
    walk order: the deterministic answer a consumer diffs. A requirement now
    carries only the refs of its own front matter — the actor it names and the
    goal it derives from — so everything that implements or realizes it sits
    upstream and must not appear. The diamond onto `actor:customer`, reached
    directly and again through the goal's `stakeholders`, appears as its own
    two routes."""
    document = _document("req:cancel-orders", "--down")

    assert [_steps(path) for path in document["paths"]] == [
        (("actors", "down", "actor:customer"),),
        (("derives_from", "down", "goal:cheap-orders"),),
        (
            ("derives_from", "down", "goal:cheap-orders"),
            ("stakeholders", "down", "actor:customer"),
        ),
    ]
    # A diamond is not a cycle: neither route revisits an element already on
    # it, so nothing is declined on the way down.
    assert document["cycle_hit"] is False


def test_up_follows_only_refs_pointing_at_the_start() -> None:
    """The upstream side of the same requirement is the behavior realizing it
    and the component implementing it, and onward from that component
    everything naming it: the behaviors observing it, the child component, the
    interface it declares, the data it owns, the decision made about it and
    the milestone scoping it. The heavier side of the walk, since the model
    moved the cross-element links out of the element they point at."""
    document = _document("req:cancel-orders", "--up")

    assert [_steps(path) for path in document["paths"]] == [
        (("realizes", "up", "behavior:order-cancelled"),),
        (
            ("realizes", "up", "behavior:order-cancelled"),
            ("includes", "up", "milestone:m1"),
        ),
        (("implements", "up", "component:orders"),),
        (
            ("implements", "up", "component:orders"),
            ("at", "up", "behavior:order-cancelled"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("at", "up", "behavior:order-cancelled"),
            ("includes", "up", "milestone:m1"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("at", "up", "behavior:order-placed"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("at", "up", "behavior:order-placed"),
            ("supersedes", "up", "behavior:order-placed-v2"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("at", "up", "behavior:order-placed"),
            ("at", "up", "behavior:order-placed-v2"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("parent", "up", "component:cancellation"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("parent", "up", "component:cancellation"),
            ("scope", "up", "quality:cancel-latency"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("parent", "up", "component:cancellation"),
            ("scope", "up", "quality:cancel-latency"),
            ("must_hold", "up", "milestone:m1"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("parent", "up", "component:cancellation"),
            ("scope", "up", "milestone:m1"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("declared_by", "up", "interface:order-events"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("declared_by", "up", "interface:order-events"),
            ("calls", "up", "component:cancellation"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("declared_by", "up", "interface:order-events"),
            ("calls", "up", "component:cancellation"),
            ("scope", "up", "quality:cancel-latency"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("declared_by", "up", "interface:order-events"),
            ("calls", "up", "component:cancellation"),
            ("scope", "up", "quality:cancel-latency"),
            ("must_hold", "up", "milestone:m1"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("declared_by", "up", "interface:order-events"),
            ("calls", "up", "component:cancellation"),
            ("scope", "up", "milestone:m1"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("owner_component", "up", "data:order"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("applies_to", "up", "decision:event-log"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("applies_to", "up", "decision:event-log"),
            ("must_hold", "up", "milestone:m1"),
        ),
        (
            ("implements", "up", "component:orders"),
            ("scope", "up", "milestone:m1"),
        ),
    ]


def test_up_and_down_together_is_the_default_both_direction_walk() -> None:
    """Both flags at once is redundant, not contradictory: the spec's default
    for neither flag, and byte-identical to it."""
    both = _trace("req:cancel-orders", "--up", "--down", "--format", "json")
    default = _trace("req:cancel-orders", "--format", "json")

    assert both.exit_code == ExitCode.OK
    assert both.stdout == default.stdout


def test_the_walk_reports_the_hops_it_declined_as_a_cycle_hit() -> None:
    """`component:cancellation` satisfies the quality whose own `scope` names
    it back — a reciprocal pair the schema invites, one half a relationship
    edge and the other half a field. The upward walk arrives at the quality
    through `scope` and declines the `satisfies` hop back rather than looping,
    and says so: `cycle_hit` is information about the shape of the graph,
    `ab check`'s `integrity/cycle` rule is the judgement about which relations
    may loop."""
    assert _document("req:cancel-orders", "--up")["cycle_hit"] is True


def test_the_addendums_edges_join_the_downward_walk_too() -> None:
    """Downward from a behavior every edge kind it carries is a first hop:
    `supersedes` to the behavior it replaces, an observation's `at` to what it
    watches (a resource, a component, or another behavior — composition), and
    `realizes` to the requirement. `iter_references` yields all of them, so no
    trace-side kind filter could drop one without the index noticing."""
    # Split across the two behaviors that carry them: the replacement states
    # no `realizes` of its own, so the requirement hop is read off the
    # cancelling behavior instead.
    replacement = [
        _steps(path) for path in _document("behavior:order-placed-v2", "--down")["paths"]
    ]
    cancelling = [_steps(path) for path in _document("behavior:order-cancelled", "--down")["paths"]]

    assert (("supersedes", "down", "behavior:order-placed"),) in replacement
    assert (("at", "down", "behavior:order-placed"),) in replacement
    assert (("at", "down", "resource:order-stream"),) in replacement
    assert (("realizes", "down", "req:cancel-orders"),) in cancelling
    assert (("at", "down", "component:orders"),) in cancelling


# --- the formats -----------------------------------------------------------------


def test_json_envelopes_the_answer() -> None:
    to = _document("req:cancel-orders", "--to", "decision:event-log")
    without = _document("req:cancel-orders")

    assert to["from"] == "req:cancel-orders"
    assert to["to"] == "decision:event-log"
    assert without["to"] is None


def test_json_folds_into_a_default_format_only() -> None:
    folded = _trace("req:cancel-orders", "--up", "--json")
    explicit_text = _trace("req:cancel-orders", "--up", "--format", "text", "--json")
    explicit_mermaid = _trace("req:cancel-orders", "--up", "--format", "mermaid", "--json")

    assert folded.exit_code == ExitCode.OK
    assert json.loads(folded.stdout)["paths"]
    assert explicit_text.stdout.startswith("req:cancel-orders <--realizes--")
    assert explicit_mermaid.stdout.startswith("graph TD")


def test_text_spells_each_path_as_one_line_with_directional_arrows() -> None:
    """A hop reads left to right along the path: `-->` for a ref the left
    element carries, `<--` for a hop against one the right element carries."""
    result = _trace("req:cancel-orders", "--to", "decision:event-log")

    assert result.exit_code == ExitCode.OK
    assert (
        "req:cancel-orders <--implements-- component:orders"
        " <--declared_by-- interface:order-events <--calls-- component:cancellation"
        " <--scope-- milestone:m1 --must_hold--> decision:event-log"
    ) in result.stdout.splitlines()


def test_text_notes_the_cycle_hit_and_nothing_else_when_empty() -> None:
    """The note is the last line of a text answer, and only silence prints
    when no path exists — no blank line where a path would be."""
    up = _trace("req:cancel-orders", "--up")

    assert up.exit_code == ExitCode.OK
    assert up.stdout.splitlines()[-1] == CYCLE_NOTE

    empty = _trace("req:cancel-orders", "--to", "term:order")

    assert empty.exit_code == ExitCode.OK
    assert empty.stdout == ""


def test_mermaid_is_one_graph_td_block_of_refs_and_relations() -> None:
    """Nodes first in first-appearance order, then labelled edges — the same
    emitter `ab render --format mermaid` will call (docs/tasks/27-render-
    diagrams.md), pinned here so the two cannot drift apart. Mermaid node ids
    cannot carry the `:` a ref is spelled with, so the id is the ref with
    colons flattened and the full ref rides along as the label. An edge points
    the way the walk went rather than the way the ref does, so an upward hop
    draws from the element the walk left."""
    result = _trace("req:cancel-orders", "--up", "--format", "mermaid")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "graph TD",
        '  req_cancel_orders["req:cancel-orders"]',
        '  behavior_order_cancelled["behavior:order-cancelled"]',
        '  milestone_m1["milestone:m1"]',
        '  component_orders["component:orders"]',
        '  behavior_order_placed["behavior:order-placed"]',
        '  behavior_order_placed_v2["behavior:order-placed-v2"]',
        '  component_cancellation["component:cancellation"]',
        '  quality_cancel_latency["quality:cancel-latency"]',
        '  interface_order_events["interface:order-events"]',
        '  data_order["data:order"]',
        '  decision_event_log["decision:event-log"]',
        "  req_cancel_orders -->|realizes| behavior_order_cancelled",
        "  behavior_order_cancelled -->|includes| milestone_m1",
        "  req_cancel_orders -->|implements| component_orders",
        "  component_orders -->|at| behavior_order_cancelled",
        "  component_orders -->|at| behavior_order_placed",
        "  behavior_order_placed -->|supersedes| behavior_order_placed_v2",
        "  behavior_order_placed -->|at| behavior_order_placed_v2",
        "  component_orders -->|parent| component_cancellation",
        "  component_cancellation -->|scope| quality_cancel_latency",
        "  quality_cancel_latency -->|must_hold| milestone_m1",
        "  component_cancellation -->|scope| milestone_m1",
        "  component_orders -->|declared_by| interface_order_events",
        "  interface_order_events -->|calls| component_cancellation",
        "  component_orders -->|owner_component| data_order",
        "  component_orders -->|applies_to| decision_event_log",
        "  decision_event_log -->|must_hold| milestone_m1",
        "  component_orders -->|scope| milestone_m1",
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
    result = _trace("req:cancel-orders", "--to", "decision:never-made")

    assert result.exit_code == ExitCode.USAGE
    assert "--to" in result.stderr
    assert result.stdout == ""
