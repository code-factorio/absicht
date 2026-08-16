"""``ab render``: the read-only site — element pages, traceability, gaps.

What these tests pin, per ``docs/tasks/26-render-site.md`` (the non-diagram
half; ``--overlay``/``--format`` are ``docs/tasks/27-render-diagrams.md``'s):

- one page per element under ``elements/<kind>/<slug>.html``, an index that
  groups them by kind the way ``ab list`` walks one kind at a time, a
  traceability page built from ``ab trace``'s traversal over the requirements,
  and a gaps page from ``ab gaps``' worklist;
- the site is internally link-consistent — every ``href`` a generated page
  carries resolves to a file in the output, the cheap no-browser smoke test
  the spec asks for;
- ``--scope REF`` shrinks every page to the subtree reachable from ``REF``
  following refs outward: fewer element pages, and a ref outside the scope
  stays plain text on a page rather than linking to a page that does not
  exist;
- an explicit ``--overlay``/``--format`` still reports "not implemented yet" —
  the diagram half of this one command — which is also why ``render`` stays
  out of ``IMPLEMENTED`` in ``tests/test_cli.py`` until that task lands;
- an unknown ``--scope`` ref is ``USAGE``, the lookup miss ``show`` and
  ``trace`` already map there;
- ``--json`` is the ``schema_version`` envelope of ``00-conventions.md``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from absicht.cli import app, query
from absicht.cli._common import ExitCode
from absicht.models import SCHEMA_VERSION

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"
BROWNFIELD = FIXTURES / "brownfield"

# clean/'s twelve elements plus the three whole-store views. A page's path is
# its id with the kind as a directory — one directory per kind, like the store.
CLEAN_PAGES = {
    "index.html",
    "gaps.html",
    "trace.html",
    "elements/system/acme.html",
    "elements/requirement/browse-catalog.html",
    "elements/requirement/cancel-orders.html",
    "elements/story/cancel-order.html",
    "elements/component/cancellation.html",
    "elements/component/catalog.html",
    "elements/component/orders.html",
    "elements/seam/order-events.html",
    "elements/data/order.html",
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


def test_one_page_per_element_plus_the_three_whole_store_views(tmp_path: Path) -> None:
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
    assert "Take orders and record what happened to them." in index


def test_an_element_page_is_the_show_view_with_links(tmp_path: Path) -> None:
    """The page is `ab show`'s neighbourhood — same fields, same two sides,
    each neighbour named with its field — with every in-scope ref a link."""
    result = _render(CLEAN, tmp_path)

    assert result.exit_code == ExitCode.OK
    page = (tmp_path / "elements" / "component" / "orders.html").read_text(encoding="utf-8")
    assert "<h1>Orders</h1>" in page
    assert "<code>component:orders</code>" in page
    assert "responsibility: Take orders and record what happened to them." in page
    assert '<a href="../component/catalog.html">component:catalog</a> — contains' in page
    assert '<a href="../decision/event-log.html">decision:event-log</a> — applies_to' in page


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


def test_scope_renders_only_the_subtree(tmp_path: Path) -> None:
    """`component:catalog` points at nothing, so its subtree is itself alone:
    the smallest site that is still a site, provable by which pages exist."""
    result = _render(CLEAN, tmp_path, "--scope", "component:catalog")

    assert result.exit_code == ExitCode.OK
    assert _pages(tmp_path) == {
        "index.html",
        "gaps.html",
        "trace.html",
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
    assert 'href="../component/orders.html"' not in page


@pytest.mark.parametrize("flags", [["--overlay", "state"], ["--format", "mermaid"]])
def test_the_diagram_half_is_still_not_implemented(tmp_path: Path, flags: list[str]) -> None:
    """Asking for diagrams explicitly is refused whole, not honoured halfway:
    an unpinned or uncoloured diagram would quietly defeat the purpose both
    diagram flags exist for."""
    result = _render(CLEAN, tmp_path, *flags)

    assert result.exit_code == ExitCode.INTERNAL
    assert "not implemented yet" in result.stderr
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
