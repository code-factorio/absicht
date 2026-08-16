"""``absicht.render``: the read-only projections behind ``ab show``,
``ab gaps`` and ``ab trace``, and the site those pages become.

The command contracts — exit codes, flags, the bytes on stdout — live in
``tests/test_show_cli.py``, ``tests/test_gaps_cli.py``,
``tests/test_trace_cli.py`` and ``tests/test_render_cli.py``. What is pinned
here is the projections themselves, the shapes ``docs/tasks/26-render-site.md``
builds on ("literally reuse" the show view; "a gaps page, reusing 23-gaps.md's
worklist") and the machinery the CLI tests cannot reach without a socket or
a clock:

- ``--depth`` bounds the *outgoing* side only; the inbound side is one hop at
  any depth, because expanding both directions is the pathfinding ``ab trace``
  owns and ``show`` deliberately does not (``docs/tasks/21-show.md`` left the
  choice open; this is the one it made, and the command's ``--help`` says so);
- expansion stops when the budget runs out, not when a walk revisits a node —
  a seam's provider provides that seam right back, and the view of a cyclic
  graph is a bounded tree, not a search;
- a dangling ref resolves to no neighbour on either side, the same policy
  ``Index.referenced_by`` already holds: reporting dangling refs is ``ab
  check``'s job. ``broken/`` cannot reach this through the CLI (its two
  unreadable files are ``build``'s refusal), so the policy is pinned here on
  the folded design;
- the gaps worklist's date boundaries — the ones no fixture holds, because a
  fixture pinned to "today" would rot: a question turns overdue strictly after
  its due date, an external expires strictly after its expiry date, and a
  question a decision has already resolved leaves the worklist;
- the trace walk's cycle guard: a hop onto an element already on the current
  path is declined rather than followed, so a cyclic graph answers a bounded
  set of simple paths and says the guard fired instead of hanging;
- the site's byte determinism, with the clock injected rather than read, and
  the preview server's change detection and socket behaviour, decoupled from
  the poll loop's timing — the two things ``docs/tasks/26-render-site.md``
  names as too flaky to test through the loop itself.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

import pytest

from absicht.load import load_store
from absicht.models import (
    SCHEMA_VERSION,
    Component,
    Design,
    External,
    ExternalKind,
    Question,
    State,
    System,
)
from absicht.render import (
    SiteServer,
    UnknownRefError,
    generate_site,
    neighbourhood,
    store_changed,
    store_snapshot,
    trace_paths,
    worklist,
)
from absicht.resolve import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "systems"


@pytest.fixture
def clean() -> Design:
    """The folded ``clean/`` design the assertions below walk."""
    return resolve(load_store(FIXTURES / "clean"))


def test_an_unknown_ref_raises_rather_than_answering_empty(clean: Design) -> None:
    """`ab show` maps this to `USAGE`: the caller asked for an element that is
    not there, which is a broken invocation, not a finding about the design."""

    with pytest.raises(UnknownRefError, match="component:ghost"):
        neighbourhood(clean, "component:ghost", depth=1)


def test_the_outgoing_side_expands_to_the_asked_depth_and_no_further(clean: Design) -> None:
    view = neighbourhood(clean, "seam:order-events", depth=2)

    assert [(hop.field, hop.other.id) for hop in view.outgoing] == [
        ("provider", "component:orders"),
        ("consumers", "component:cancellation"),
        ("carries", "data:order"),
    ]
    orders = view.outgoing[0]
    assert [(hop.field, hop.other.id) for hop in orders.deeper] == [
        ("contains", "component:catalog"),
        ("provides", "seam:order-events"),
        ("owns_data", "data:order"),
    ]
    # Depth 2 stops at the fringe: `orders` provides this very seam right
    # back — the cycle the budget must bound, not chase — and every hop at the
    # fringe is a leaf. Expanding those again is depth 3's job.
    assert all(hop.deeper == () for hop in orders.deeper)


def test_depth_zero_leaves_the_outgoing_side_unfollowed(clean: Design) -> None:
    """Zero hops means the element's own refs are not followed — the view is
    the element plus whoever points at it, and `--depth 0` must not quietly
    mean the same as the default."""

    view = neighbourhood(clean, "component:cancellation", depth=0)

    assert view.outgoing == ()
    assert view.incoming != ()


def test_depth_three_reaches_a_third_hop(clean: Design) -> None:
    """The budget decrements once per level, not once per two: the seam that
    `orders` provides right back gets its own outgoing edges at the third
    hop. The cycle makes this the sharp end of the depth arithmetic — one
    level early or late and the fringe moves."""

    view = neighbourhood(clean, "seam:order-events", depth=3)

    provides = view.outgoing[0].deeper[1]
    assert (provides.field, provides.other.id) == ("provides", "seam:order-events")
    assert [hop.other.id for hop in provides.deeper] == [
        "component:orders",
        "component:cancellation",
        "data:order",
    ]


def test_the_inbound_side_stays_one_hop_at_any_depth(clean: Design) -> None:
    """A depth that deep would find more if the inbound side expanded too —
    `story:cancel-order` is satisfied by nothing here, but `seam:order-events`
    is pointed at by three elements whose own refs go further out."""

    view = neighbourhood(clean, "seam:order-events", depth=5)

    assert [(link.field, link.other.id) for link in view.incoming] == [
        ("touches", "story:cancel-order"),
        ("consumes", "component:cancellation"),
        ("provides", "component:orders"),
    ]


def test_a_dangling_ref_resolves_to_no_neighbour() -> None:
    design = resolve(load_store(FIXTURES / "broken"))

    view = neighbourhood(design, "component:dangling", depth=2)

    # `dangling`'s one ref is `contains: component:ghost`, which no file
    # defines: it must not appear as a neighbour, and the empty view is still
    # a successful one — `ab show` reports neighbourhoods, `ab check` reports
    # the ghost.
    assert view.outgoing == ()


def test_json_carries_the_full_view_and_the_body_flag(clean: Design) -> None:
    view = neighbourhood(clean, "requirement:cancel-orders", depth=2)

    with_body = view.render_json(include_body=True)
    without_body = view.render_json(include_body=False)

    assert with_body["schema_version"] == SCHEMA_VERSION
    assert with_body["element"]["body"].startswith("A customer may cancel")
    assert "body" not in without_body["element"]
    hop = with_body["points_at"][0]
    assert hop["field"] == "realized_by"
    assert hop["target"]["id"] == "component:cancellation"
    # Neighbours carry their fields but never prose or provenance: the body is
    # the focus element's, and where a neighbour lives is `source`'s story.
    assert "body" not in hop["target"]
    assert "source" not in hop["target"]
    assert [(deeper["field"], deeper["target"]["id"]) for deeper in hop["deeper"]] == [
        ("consumes", "seam:order-events")
    ]
    assert hop["deeper"][0]["deeper"] == []
    assert [(link["field"], link["source"]["id"]) for link in with_body["referenced_by"]] == [
        ("satisfies", "story:cancel-order")
    ]


# --- the gaps worklist --------------------------------------------------------

# The three worklist boundaries no fixture can hold: each would need "today"
# baked into the store, and rot the day after. Hand-built designs instead,
# with the clock injected the way `ab check`'s policy layer already runs.
TODAY = date(2026, 8, 16)


def test_worklist_marks_delegated_elements_unfinished() -> None:
    """`delegated` is the third unfinished state and the one no fixture holds:
    decided-elsewhere is still unfinished, and without an owner the element is
    on the list twice over."""
    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
        components=(
            Component(id="component:outsourced", title="Outsourced", state=State.DELEGATED),
        ),
    )

    (only,) = worklist(design, today=TODAY)

    assert only.element.id == "component:outsourced"
    assert only.reasons == ("state=delegated", "unowned")


def test_worklist_questions_turn_overdue_strictly_after_their_due_date() -> None:
    """A question due today is still open — the day itself is inside the ask,
    the same strict comparison `check` spells for expiry — and a question a
    decision has already resolved is nobody's worklist entry, whatever its
    state says."""
    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
        questions=(
            Question(id="question:today", title="Today", owner="a", due_on=TODAY),
            Question(
                id="question:yesterday",
                title="Yesterday",
                owner="a",
                due_on=TODAY - timedelta(days=1),
            ),
            Question(
                id="question:closed",
                title="Closed",
                owner="a",
                state=State.SPECIFIED,
                due_on=TODAY - timedelta(days=1),
                resolved_by="decision:done",
            ),
        ),
    )

    by_id = {gap.element.id: gap for gap in worklist(design, today=TODAY)}

    assert by_id["question:today"].reasons == ("state=unknown", "question-open")
    assert by_id["question:yesterday"].reasons == ("state=unknown", "question-overdue")
    # The date the reason hangs on travels with the entry, past or not.
    assert by_id["question:today"].due_on == TODAY
    assert by_id["question:yesterday"].due_on == TODAY - timedelta(days=1)
    assert "question:closed" not in by_id


def test_worklist_expires_an_external_strictly_after_its_expiry_date() -> None:
    """`expires_on` means "after this, re-check": the day itself is still
    trusted — `absicht.check`'s reading, and necessarily this one's too,
    because the worklist reuses that module's one spelling of "expired"
    rather than re-deriving the comparison."""
    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
        externals=(
            External(
                id="external:today",
                title="Today",
                state=State.SPECIFIED,
                owner="ops",
                external_kind=ExternalKind.SERVICE,
                expires_on=TODAY,
            ),
            External(
                id="external:yesterday",
                title="Yesterday",
                state=State.SPECIFIED,
                owner="ops",
                external_kind=ExternalKind.SERVICE,
                expires_on=TODAY - timedelta(days=1),
            ),
        ),
    )

    (only,) = worklist(design, today=TODAY)

    assert only.element.id == "external:yesterday"
    assert only.reasons == ("external-expired",)
    assert only.expires_on == TODAY - timedelta(days=1)


# --- the trace paths -----------------------------------------------------------


def test_a_cycle_ends_the_walk_and_says_so() -> None:
    """`broken/`'s `contains` cycle is the input the walk must survive: the
    guard is the simple-path invariant — a hop onto an element already on the
    current path is declined — so the answer is a bounded set of paths plus
    `cycle_hit`, not a hang. Exactly the two one-hop paths exist (down
    through the edge loop-a authors, up through the one loop-b authors); the
    hop back is declined both ways. `broken/` cannot reach this through the
    CLI (its two unreadable files are `build`'s refusal), so the guard is
    pinned here on the folded design."""
    design = resolve(load_store(FIXTURES / "broken"))

    result = trace_paths(design, "component:loop-a")

    assert [tuple((step.field, step.up, step.ref) for step in path) for path in result.paths] == [
        (("contains", False, "component:loop-b"),),
        (("contains", True, "component:loop-b"),),
    ]
    assert result.cycle_hit is True


def test_an_unknown_to_ref_raises_rather_than_answering_empty(clean: Design) -> None:
    """`ab trace` maps this to `USAGE`: "no path to a nonexistent element" is
    not an answer anyone should be able to mistake for a route check."""
    with pytest.raises(UnknownRefError, match="decision:never"):
        trace_paths(clean, "requirement:cancel-orders", to="decision:never-made")


# --- the site --------------------------------------------------------------------


def test_an_unknown_scope_ref_raises_rather_than_rendering_everything(
    clean: Design, tmp_path: Path
) -> None:
    """An ignored `--scope` would quietly render the whole store — the same
    empty-answer trap `show` and `trace` refuse, so the site refuses it too."""
    with pytest.raises(UnknownRefError, match="component:ghost"):
        generate_site(clean, tmp_path, today=TODAY, scope="component:ghost")


def _site_bytes(out: Path) -> dict[str, bytes]:
    """The site as ``path → bytes``: the shape a determinism claim compares."""
    return {
        path.relative_to(out).as_posix(): path.read_bytes() for path in sorted(out.rglob("*.html"))
    }


def test_the_site_is_byte_identical_across_runs(clean: Design, tmp_path: Path) -> None:
    """`today` is injected rather than read, so nothing between the store and
    the bytes reads a clock: the same design spells the same site twice — the
    property `docs/maintainers/verification.md`'s determinism job cross-checks
    from a clean checkout."""

    generate_site(clean, tmp_path / "first", today=TODAY)
    generate_site(clean, tmp_path / "second", today=TODAY)

    first = _site_bytes(tmp_path / "first")
    assert first == _site_bytes(tmp_path / "second")
    assert len(first) == 15  # twelve element pages, index, traceability, gaps


def test_the_change_detection_notices_edits_additions_and_removals(tmp_path: Path) -> None:
    """The poll loop's whole judgement in one pair of functions, decoupled from
    the loop: docs/tasks/26-render-site.md asks for exactly this unit test
    instead of a timing-dependent one on the server itself."""

    store = tmp_path / "store"
    (store / "requirements").mkdir(parents=True)
    element = store / "requirements" / "r.md"
    element.write_text("---\nid: requirement:r\n---\n", encoding="utf-8")

    before = store_snapshot(store)
    assert not store_changed(store, before)

    # A touch far from any plausible real mtime, so the verdict is the
    # detection's, not the filesystem's.
    os.utime(element, ns=(2**40, 2**40))
    assert store_changed(store, before)

    (store / "system.yaml").write_text("id: system:s\n", encoding="utf-8")
    assert store_changed(store, before)

    after = store_snapshot(store)
    element.unlink()
    assert store_changed(store, after)


def test_the_preview_server_serves_the_site_and_stops_cleanly(
    clean: Design, tmp_path: Path
) -> None:
    """The spec's `--serve` minimum: starts, serves the index page (and a
    nested element page, proving the directory mapping), shuts down cleanly.
    Port 0 asks for an ephemeral one so the test never collides."""
    out = tmp_path / "site"
    generate_site(clean, out, today=TODAY)
    server = SiteServer(out, 0)

    server.start()
    try:
        assert server.port > 0
        with urlopen(f"http://127.0.0.1:{server.port}/index.html") as response:
            assert response.status == 200
            assert response.read() == (out / "index.html").read_bytes()
        with urlopen(f"http://127.0.0.1:{server.port}/elements/component/orders.html") as nested:
            assert nested.status == 200
    finally:
        server.stop()
