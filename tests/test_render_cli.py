"""``ab render``: the read-only site — element pages, traceability, gaps, the
note inbox — and the diagrams of ``docs/tasks/27-render-diagrams.md``.

What these tests pin, per ``docs/tasks/26-render-site.md`` (the site half),
``27-render-diagrams.md`` (the diagram half) and ``60-addendum-render.md``
(the addendum's additions to both):

- one page per element under ``elements/<kind>/<slug>.html``, an index that
  groups them by kind the way ``ab list`` walks one kind at a time, a
  traceability page built from ``ab trace``'s traversal over the requirements,
  a gaps page from ``ab gaps``' worklist, and the note inbox from the store's
  ``notes/`` — notes are not elements, so they reach the page only through
  the command's own load of the store;
- a behavior page carries the addendum's own reading: the observation table
  with the resolved timing, the derived scope, realizes links, composition
  both ways, and a superseded behavior is visibly badged with links to its
  replacements — the replacement's page cross-links back;
- traceability is not only the paths page: requirement pages list their
  realizing behaviors, and component/resource/seam pages list the behaviors
  whose observations touch them — the must-not-break question, visually;
- the gaps page joins behaviors and resources exactly as ``ab gaps`` does —
  by state, plus the zero-observations line;
- the site is internally link-consistent — every ``href`` a generated page
  carries resolves to a file in the output, the cheap no-browser smoke test
  the spec asks for;
- ``--scope REF`` shrinks every page to the subtree reachable from ``REF``
  following refs outward: fewer element pages, and a ref outside the scope
  stays plain text on a page rather than linking to a page that does not
  exist;
- an explicit ``--format`` or any ``--overlay`` asks for the diagram half:
  one file per variant under ``--out``, the overlay spelling the file's name;
- a store without pinned positions is ``FINDINGS`` with a pointer at
  ``ab layout``, never an unpinned diagram — an unpinned diagram would defeat
  the whole purpose of pinning positions;
- ``--serve`` previews the site only: it is a usage error beside diagram
  flags, which write their files once rather than being watched;
- an unknown ``--scope`` ref is ``USAGE``, the lookup miss ``show`` and
  ``trace`` already map there;
- ``--json`` is the ``schema_version`` envelope of ``00-conventions.md``.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

from absicht.cli import app, query
from absicht.cli._common import ExitCode
from absicht.models import SCHEMA_VERSION

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"
BROWNFIELD = FIXTURES / "brownfield"

# clean/'s fifteen elements plus the four whole-store views. A page's path is
# its id with the kind as a directory — one directory per kind, like the store.
CLEAN_PAGES = {
    "index.html",
    "gaps.html",
    "trace.html",
    "notes.html",
    "elements/system/acme.html",
    "elements/requirement/browse-catalog.html",
    "elements/requirement/cancel-orders.html",
    "elements/story/cancel-order.html",
    "elements/component/cancellation.html",
    "elements/component/catalog.html",
    "elements/component/orders.html",
    "elements/seam/order-events.html",
    "elements/data/order.html",
    "elements/resource/order-cache.html",
    "elements/behavior/catalog-browsable.html",
    "elements/behavior/order-placed-v2.html",
    "elements/behavior/order-placed.html",
    "elements/decision/event-log.html",
    "elements/milestone/m1.html",
}

# The index's kind sections, in `Design` field order — the order the store's
# kinds arrive in, which is the grouping `ab list` implies by walking one kind
# at a time.
KIND_ORDER = [
    "system",
    "requirement",
    "story",
    "component",
    "seam",
    "data",
    "resource",
    "behavior",
    "decision",
    "milestone",
]

HREF = re.compile(r'href="([^"]+)"')


def _render(store: Path, out: Path, *flags: str) -> Any:
    return runner.invoke(app, ["--store", str(store), "render", "--out", str(out), *flags])


def _pages(out: Path) -> set[str]:
    """Every page the site holds, as paths from the site root."""
    return {path.relative_to(out).as_posix() for path in out.rglob("*.html")}


def _assert_links_resolve(out: Path) -> None:
    """The spec's link-consistency smoke test: every href this site generated
    resolves to a file in the output, so no page points at nothing."""
    for page in sorted(out.rglob("*.html")):
        for href in HREF.findall(page.read_text(encoding="utf-8")):
            assert (page.parent / href).is_file(), (
                f"{page.name} links to {href}, which is not there"
            )


def test_one_page_per_element_plus_the_whole_store_views(tmp_path: Path) -> None:
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    assert _pages(tmp_path) == CLEAN_PAGES


@pytest.mark.parametrize(
    "flags",
    [[], ["--scope", "component:orders"]],
    ids=["whole-store", "scoped"],
)
def test_every_generated_link_resolves(tmp_path: Path, flags: list[str]) -> None:
    """Also scoped: the subtree shrinks the site, and the pages it keeps must
    not reach outside it with a link — out-of-scope refs stay plain text."""
    result = _render(CLEAN, tmp_path, *flags)

    assert result.exit_code == ExitCode.OK
    _assert_links_resolve(tmp_path)


def test_the_index_groups_elements_by_kind_in_design_order(tmp_path: Path) -> None:
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert [line for line in index.splitlines() if line.startswith("<h2>")] == [
        f"<h2>{kind}</h2>" for kind in KIND_ORDER
    ]
    assert 'href="elements/component/orders.html">component:orders</a>' in index
    assert ">component:orders</a> — Orders</li>" in index


def test_an_element_page_is_the_show_view_with_links(tmp_path: Path) -> None:
    """The page is `ab show`'s neighbourhood — same fields, same two sides,
    each neighbour named with its field — with every in-scope ref a link."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = (tmp_path / "elements" / "component" / "orders.html").read_text(encoding="utf-8")
    assert "<h1>Orders</h1>" in page
    assert "<code>component:orders</code>" in page
    assert "responsibility: Take orders and record what happened to them." in page
    assert (
        '<a href="../../elements/component/catalog.html">component:catalog</a> — contains' in page
    )
    assert (
        '<a href="../../elements/decision/event-log.html">decision:event-log</a> — applies_to'
        in page
    )


def test_an_element_page_carries_the_prose_body(tmp_path: Path) -> None:
    """`body` is never parsed, only carried — on a page it becomes headings
    and paragraphs, the subset the store's prose actually uses."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    requirement = (tmp_path / "elements" / "requirement" / "cancel-orders.html").read_text(
        encoding="utf-8"
    )
    assert "<p>A customer may cancel an order while it can still be refunded.</p>" in requirement
    decision = (tmp_path / "elements" / "decision" / "event-log.html").read_text(encoding="utf-8")
    assert "<h2>Context</h2>" in decision


def _page(out: Path, *parts: str) -> str:
    """One generated page's bytes, by its path under the site root."""
    return out.joinpath(*parts).read_text(encoding="utf-8")


def test_a_behavior_page_spells_the_observation_table(tmp_path: Path) -> None:
    """The page reuses the show view, so a behavior's observations arrive as
    the addendum's table — statement, at (linked), outcome, and the *effective*
    timing: the §1.2 default when the author said nothing, never the raw
    field, and no when at all for `must_not`."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = _page(tmp_path, "elements", "behavior", "order-placed-v2.html")
    assert "<h2>Observations</h2>" in page
    assert "<tr><th>statement</th><th>at</th><th>outcome</th><th>effective timing</th></tr>" in page
    # obs-1 authored `immediate`; obs-2 authored `eventual` — both carry their
    # authored values, and the `at` cell links to the page it names.
    assert (
        "<tr><td>The order appears in the order cache</td>"
        '<td><a href="../../elements/resource/order-cache.html">resource:order-cache</a></td>'
        "<td>must</td><td>immediate</td></tr>"
    ) in page
    assert (
        "<tr><td>The order shows in the customer&#x27;s order list</td>"
        '<td><a href="../../elements/component/orders.html">component:orders</a></td>'
        "<td>must</td><td>eventual</td></tr>"
    ) in page
    # `must_not` means at no point: the timing cell stays empty of a when.
    assert "<tr><td>No order is cached before payment clears</td>" in page
    assert "<td>must_not</td><td>—</td></tr>" in page
    # obs-5 says nothing about timing: the effective one follows its `at`, a
    # component — immediate.
    assert "<td>should</td><td>immediate</td></tr>" in page
    assert '"statement"' not in page


def test_a_superseded_behavior_page_badges_itself_and_cross_links_its_replacement(
    tmp_path: Path,
) -> None:
    """§5's visible mark on the page: a superseded behavior is not deleted but
    must not read as current — its page says so up top and links to its derived
    replacements, and the replacement's page links back through its stored
    `supersedes`."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    superseded = _page(tmp_path, "elements", "behavior", "order-placed.html")
    assert (
        "<p><strong>superseded</strong> by "
        '<a href="../../elements/behavior/order-placed-v2.html">behavior:order-placed-v2</a>'
        "</p>" in superseded
    )
    replacement = _page(tmp_path, "elements", "behavior", "order-placed-v2.html")
    assert (
        '<a href="../../elements/behavior/order-placed.html">behavior:order-placed</a>'
        in replacement
    )
    # The index names it as no longer current too, the way `ab list`'s rows do.
    assert "Order placed [superseded]" in _page(tmp_path, "index.html")


def test_a_behavior_page_carries_scope_realizes_and_composition_both_ways(
    tmp_path: Path,
) -> None:
    """The addendum's derived facts, computed and never stored, additive on
    the page: the §4.1 scope (a component-only behavior is `local`, the
    cache-and-component one is `system`), the `realizes` links, and §4.2's
    composition edges in both directions."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = _page(tmp_path, "elements", "behavior", "order-placed-v2.html")
    assert "<li>scope: system</li>" in page
    assert "<h2>Realizes</h2>" in page
    assert (
        '<li><a href="../../elements/requirement/cancel-orders.html">'
        "requirement:cancel-orders</a></li>" in page
    )
    assert "<li>composes: " in page
    assert (
        'composes: <a href="../../elements/behavior/order-placed.html">behavior:order-placed</a>'
        in page
    )
    superseded = _page(tmp_path, "elements", "behavior", "order-placed.html")
    assert "<li>scope: system</li>" in superseded
    assert (
        "composed by: "
        '<a href="../../elements/behavior/order-placed-v2.html">behavior:order-placed-v2</a>'
        in superseded
    )
    local = _page(tmp_path, "elements", "behavior", "catalog-browsable.html")
    assert "<li>scope: local</li>" in local


def test_a_behavior_page_draws_its_composition_graph(tmp_path: Path) -> None:
    """§4.2 as its own small graph on the behavior's page — inline SVG, no
    script — naming the behavior and both directions' neighbours; a behavior
    with no composition edges either way gets no empty picture."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = _page(tmp_path, "elements", "behavior", "order-placed-v2.html")
    assert "<h2>Composition</h2>" in page
    svg = page[page.index("<svg") : page.index("</svg>")]
    assert "behavior:order-placed-v2" in svg
    assert "behavior:order-placed" in svg
    assert svg.count("composes") >= 1  # the edge's label, once per edge
    alone = _page(tmp_path, "elements", "behavior", "catalog-browsable.html")
    assert "<svg" not in alone


def test_the_behavior_page_is_snapshotted(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    """The golden behavior page of docs/tasks/60-addendum-render.md:
    `order-placed-v2` — composition onto a superseded predecessor, every
    observation shape, the derived scope — the page every assertion above
    reads, held to its bytes."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    assert _page(tmp_path, "elements", "behavior", "order-placed-v2.html") == snapshot


def test_a_resource_page_lists_the_behaviors_observing_it(tmp_path: Path) -> None:
    """A resource is what its observations give meaning (§1.4): its page lists
    the behaviors whose observations touch it — the site-side reading of the
    reverse refs, the must-not-break question — with a superseded one marked
    so it cannot read as current."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = _page(tmp_path, "elements", "resource", "order-cache.html")
    assert "<h2>Observing behaviors</h2>" in page
    assert (
        '<li><a href="../../elements/behavior/order-placed-v2.html">behavior:order-placed-v2</a>'
        " — Order placed through checkout</li>" in page
    )
    assert (
        '<li><a href="../../elements/behavior/order-placed.html">behavior:order-placed</a>'
        " [superseded] — Order placed</li>" in page
    )


def test_the_resource_page_is_snapshotted(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    """The golden resource page: fields, the observing behaviors, the prose."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    assert _page(tmp_path, "elements", "resource", "order-cache.html") == snapshot


def test_a_requirement_page_lists_its_realizing_behaviors(tmp_path: Path) -> None:
    """Traceability on the page the requirement owns: the behaviors whose
    `realizes` names it, not only the components `realized_by` carries."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = _page(tmp_path, "elements", "requirement", "cancel-orders.html")
    assert "<h2>Realizing behaviors</h2>" in page
    assert "behavior:order-placed-v2" in page
    assert "behavior:order-placed" in page
    browse = _page(tmp_path, "elements", "requirement", "browse-catalog.html")
    assert '<a href="../../elements/behavior/catalog-browsable.html">' in browse


def test_a_component_page_lists_the_behaviors_observing_it(tmp_path: Path) -> None:
    """The seam/component side of the same reading: `component:orders` is
    touched by `order-placed-v2`'s eventual observation, and its page says
    so — what a packet's must-not-break list is derived from, visible where
    the work happens."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = _page(tmp_path, "elements", "component", "orders.html")
    assert "<h2>Observing behaviors</h2>" in page
    assert (
        '<a href="../../elements/behavior/order-placed-v2.html">behavior:order-placed-v2</a>'
        in page
    )


def test_the_traceability_page_links_requirements_to_what_realizes_them(
    tmp_path: Path,
) -> None:
    """`ab trace`'s traversal, rendered per requirement — the spec's own
    example chain, with both directions' arrows spelled."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = (tmp_path / "trace.html").read_text(encoding="utf-8")
    assert "—realized_by→" in page
    assert "←satisfies—" in page
    assert 'href="elements/component/cancellation.html">component:cancellation</a>' in page


def test_the_gaps_page_is_the_worklist(tmp_path: Path) -> None:
    result = _render(BROWNFIELD, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = (tmp_path / "gaps.html").read_text(encoding="utf-8")
    assert "external:payment-api" in page
    assert "external-expired (expired 2026-01-01)" in page
    assert "question-overdue (due 2026-01-10)" in page


def test_a_complete_store_has_an_empty_gaps_page(tmp_path: Path) -> None:
    """`clean/` is meant to be complete: the page still exists — a missing
    page would read as "render forgot the gaps" — and says there is nothing."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    assert "no gaps" in (tmp_path / "gaps.html").read_text(encoding="utf-8")


def test_the_gaps_page_joins_behaviors_and_resources_like_ab_gaps(tmp_path: Path) -> None:
    """The addendum's kinds on the worklist the page projects, never a second
    implementation of it: a behavior joins through its unfinished state and
    through having nothing observable, a resource through its state — the same
    lines `ab gaps` prints for the same store."""
    store = tmp_path / "store"
    shutil.copytree(BROWNFIELD, store)
    (store / "behaviors" / "bare.md").write_text(
        "---\nid: behavior:bare\ntitle: Bare\nstate: specified\ntrigger: Something happens.\n---\n",
        encoding="utf-8",
    )
    (store / "resources").mkdir()
    (store / "resources" / "scratch.md").write_text(
        "---\nid: resource:scratch\ntitle: Scratch\nstate: unknown\n"
        "resource_kind: store\ntechnology: SQLite\n---\n",
        encoding="utf-8",
    )

    result = _render(store, tmp_path / "out")

    assert result.exit_code == ExitCode.OK
    page = (tmp_path / "out" / "gaps.html").read_text(encoding="utf-8")
    assert "behavior:reconciliation-fires" in page
    assert "state=observed" in page
    assert "behavior:bare" in page
    assert "no-observations" in page
    assert "resource:scratch" in page
    assert "state=unknown" in page


def test_the_site_carries_the_note_inbox_from_the_store(tmp_path: Path) -> None:
    """The command's own load of `notes/` reaches the page: the headline, the
    body, the anchor linked — the inbox `ab note list` prints, at reading
    width. The creation date is written relative to today because the command,
    unlike the library, reads the clock exactly once."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    created = date.today() - timedelta(days=90)
    (store / "notes").mkdir()
    (store / "notes" / "old0001.md").write_text(
        f"---\nid: note:old0001\ncreated: {created.isoformat()}\n"
        "ref: resource:order-cache\n---\n\nThe cache needs a TTL.\n",
        encoding="utf-8",
    )

    result = _render(store, tmp_path / "out")

    assert result.exit_code == ExitCode.OK
    page = (tmp_path / "out" / "notes.html").read_text(encoding="utf-8")
    assert "<p>1 note, oldest 3 months</p>" in page
    assert "<p>The cache needs a TTL.</p>" in page
    assert 'href="elements/resource/order-cache.html">resource:order-cache</a>' in page
    assert "notes.html" in (tmp_path / "out" / "index.html").read_text(encoding="utf-8")


def test_scope_renders_only_the_subtree(tmp_path: Path) -> None:
    """`component:catalog` points at nothing, so its subtree is itself alone:
    the smallest site that is still a site, provable by which pages exist."""
    result = _render(CLEAN, tmp_path, "--scope", "component:catalog")

    assert result.exit_code == ExitCode.OK
    assert _pages(tmp_path) == {
        "index.html",
        "gaps.html",
        "trace.html",
        "notes.html",
        "elements/component/catalog.html",
    }


def test_refs_outside_the_scope_stay_plain_text(tmp_path: Path) -> None:
    """`component:orders` contains `component:catalog` but has no page in the
    catalog-only scope: the ref is still named — the mini-site must not
    pretend the rest of the design does not exist — it just does not link."""
    result = _render(CLEAN, tmp_path, "--scope", "component:catalog")

    assert result.exit_code == ExitCode.OK
    page = (tmp_path / "elements" / "component" / "catalog.html").read_text(encoding="utf-8")
    assert "component:orders" in page
    assert 'href="../../elements/component/orders.html"' not in page


@pytest.fixture
def laid_out(tmp_path: Path) -> Path:
    """The clean fixture as a private copy with positions pinned by ``ab
    layout`` — the state a diagram is drawn from; the shared fixture ships
    without a ``layout.yaml`` and must stay that way."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    assert runner.invoke(app, ["--store", str(store), "layout"]).exit_code == ExitCode.OK
    return store


def test_an_explicit_format_writes_one_diagram(laid_out: Path, tmp_path: Path) -> None:
    out = tmp_path / "diagrams"

    result = _render(laid_out, out, "--format", "svg")

    assert result.exit_code == ExitCode.OK
    assert (out / "diagram.svg").read_text(encoding="utf-8").startswith("<?xml")
    assert result.stdout == f"wrote {out / 'diagram.svg'}\n"


def test_an_overlay_without_an_explicit_format_defaults_to_svg(
    laid_out: Path, tmp_path: Path
) -> None:
    out = tmp_path / "diagrams"

    result = _render(laid_out, out, "--overlay", "state")

    assert result.exit_code == ExitCode.OK
    assert (out / "diagram.svg").exists() is False
    assert (out / "diagram-state.svg").read_text(encoding="utf-8").startswith("<?xml")


def test_repeated_overlays_write_one_variant_each(laid_out: Path, tmp_path: Path) -> None:
    """One visual result per overlay, not a blend: two overlays in one
    invocation produce two files that differ from each other and from the
    uncoloured diagram."""
    out = tmp_path / "diagrams"

    result = _render(laid_out, out, "--overlay", "state", "--overlay", "coverage")

    assert result.exit_code == ExitCode.OK
    state = (out / "diagram-state.svg").read_text(encoding="utf-8")
    coverage = (out / "diagram-coverage.svg").read_text(encoding="utf-8")
    plain = _render(laid_out, tmp_path / "plain", "--format", "svg")
    assert plain.exit_code == ExitCode.OK
    assert state != coverage
    assert state != (tmp_path / "plain" / "diagram.svg").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("fmt", "first_line"),
    [("mermaid", "graph TD"), ("d2", "direction: right")],
)
def test_the_text_formats_spell_their_dsl(
    laid_out: Path, tmp_path: Path, fmt: str, first_line: str
) -> None:
    out = tmp_path / "diagrams"

    result = _render(laid_out, out, "--format", fmt)

    assert result.exit_code == ExitCode.OK
    assert (out / f"diagram.{fmt}").read_text(encoding="utf-8").startswith(first_line)


def test_rendering_without_pinned_positions_is_findings_pointing_at_ab_layout(
    tmp_path: Path,
) -> None:
    """No ``layout.yaml``, no diagram: the refusal names the command that
    pins positions, and nothing is written to stdout."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    out = tmp_path / "diagrams"

    result = _render(store, out, "--format", "svg")

    assert result.exit_code == ExitCode.FINDINGS
    assert "ab layout" in result.stderr
    assert result.stdout == ""
    assert out.exists() is False


def test_json_envelopes_the_diagram_run(laid_out: Path, tmp_path: Path) -> None:
    out = tmp_path / "diagrams"

    result = _render(laid_out, out, "--format", "svg", "--json")

    assert result.exit_code == ExitCode.OK
    document = json.loads(result.stdout)
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["out"] == str(out)
    assert document["diagrams"] == ["diagram.svg"]


def test_an_unknown_scope_ref_is_a_usage_error_for_diagrams_too(
    laid_out: Path, tmp_path: Path
) -> None:
    result = _render(
        laid_out, tmp_path / "diagrams", "--format", "svg", "--scope", "component:ghost"
    )

    assert result.exit_code == ExitCode.USAGE
    assert "--scope" in result.stderr
    assert result.stdout == ""


def test_serve_refuses_to_watch_diagrams(laid_out: Path, tmp_path: Path) -> None:
    """``--serve`` is the site's preview loop; diagrams are written once, and
    pretending to watch them would promise rebuilds that never happen."""
    result = _render(laid_out, tmp_path / "diagrams", "--format", "svg", "--serve")

    assert result.exit_code == ExitCode.USAGE
    assert "--serve" in result.stderr
    assert result.stdout == ""


def test_an_unknown_scope_ref_is_a_usage_error(tmp_path: Path) -> None:
    result = _render(CLEAN, tmp_path, "--scope", "component:ghost")

    assert result.exit_code == ExitCode.USAGE
    assert "--scope" in result.stderr
    assert result.stdout == ""


def test_json_envelopes_the_run(tmp_path: Path) -> None:
    result = _render(CLEAN, tmp_path, "--json")

    assert result.exit_code == ExitCode.OK
    document = json.loads(result.stdout)
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["out"] == str(tmp_path)
    assert document["pages"] == len(CLEAN_PAGES)


def test_text_names_the_site_and_its_size(tmp_path: Path) -> None:
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    assert result.stdout == f"wrote {tmp_path} ({len(CLEAN_PAGES)} pages)\n"


def test_an_out_of_range_port_is_a_usage_error(tmp_path: Path) -> None:
    result = _render(CLEAN, tmp_path, "--serve", "--port", "99999")

    assert result.exit_code == ExitCode.USAGE
    assert "--port" in result.stderr


def test_serve_renders_first_then_announces_the_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `--serve` wiring only, through a stand-in server: the site is on
    disk before anything listens, the bound port is the one announced, and the
    process stays in the serve loop rather than falling out of it. The server
    itself is exercised against a real socket in tests/test_render.py."""

    started: list[tuple[Path, int]] = []

    class StoppingServer:
        def __init__(self, out: Path, port: int, **_unused: object) -> None:
            started.append((out, port))

        def serve(self) -> None:
            return None

    monkeypatch.setattr(query, "SiteServer", StoppingServer)
    result = _render(CLEAN, tmp_path, "--serve", "--port", "8123")

    assert result.exit_code == ExitCode.OK
    assert _pages(tmp_path) == CLEAN_PAGES
    assert started == [(tmp_path, 8123)]
    assert "http://127.0.0.1:8123" in result.stderr
