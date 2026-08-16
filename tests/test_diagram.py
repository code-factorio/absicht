"""``absicht.diagram``: the boxes-and-edges picture of a resolved design.

The command contract — exit codes, flags, the files on disk — lives in
``tests/test_render_cli.py``. What is pinned here is the picture itself, per
``docs/tasks/27-render-diagrams.md``:

- the node set is the one ``ab layout`` positions (components, seams,
  externals) and the edges are ``contains``/``consumes``/``provides``, in a
  deterministic order — the property the CI determinism job cross-checks from
  a clean checkout is tested here as two runs spelling byte-identical SVG;
- each format is syntactically plausible for its DSL: SVG parses as XML,
  mermaid starts with a diagram keyword, d2 spells boxes and edges;
- a store without pinned positions is refused with a pointer at ``ab layout``
  rather than silently auto-laid out — an unpinned diagram would defeat the
  entire purpose of pinning positions;
- each ``--overlay`` value visibly changes the colouring, on two elements a
  fixture holds apart on that overlay's dimension. ``churn`` is the one
  overlay that reaches outside the store into git history, so its test builds
  a throwaway repository the way ``tests/test_git.py`` does — never this
  repository's own history, which drifts and is not hermetic;
- ``--scope`` limits nodes and edges to the subtree, and stops demanding
  positions for elements outside it.
"""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from absicht.diagram import Diagram, build, overlay_colours
from syrupy.assertion import SnapshotAssertion

from absicht.layout import LayoutError, compute, write_layout
from absicht.load import load_store
from absicht.models import Design, Layout, Position
from absicht.render import UnknownRefError
from absicht.resolve import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"
COMPOSITE = FIXTURES / "composite"

CLEAN_NODES = {
    "component:cancellation",
    "component:catalog",
    "component:orders",
    "seam:order-events",
}

# The renderers, keyed the way the snapshot parametrization spells the format.
RENDERERS = {
    "svg": Diagram.render_svg,
    "mermaid": Diagram.render_mermaid,
    "d2": Diagram.render_d2,
}

SVG = "{http://www.w3.org/2000/svg}"


def _laid_out(source: Path, target: Path) -> Design:
    """A private copy of ``source`` with ``layout.yaml`` pinned — the state a
    diagram is drawn from; the shared fixtures ship without one."""
    shutil.copytree(source, target)
    design = resolve(load_store(target))
    write_layout(target, compute(design))
    return design


def _picture(design: Design, root: Path, *, scope: str | None = None) -> Diagram:
    return build(design, root, scope=scope)


# --- the picture itself ---------------------------------------------------------


def test_edges_are_contains_consumes_and_provides_between_diagram_nodes(
    tmp_path: Path,
) -> None:
    """Components in id order, each field's refs in authored order: the whole
    edge set of ``clean/`` in the order every renderer spells it."""
    design = _laid_out(CLEAN, tmp_path / "store")

    picture = _picture(design, tmp_path / "store")

    assert [element.id for element in picture.nodes] == sorted(CLEAN_NODES)
    assert picture.edges == (
        ("component:cancellation", "consumes", "seam:order-events"),
        ("component:orders", "contains", "component:catalog"),
        ("component:orders", "provides", "seam:order-events"),
    )
    assert {position.ref for position in picture.positions.values()} == CLEAN_NODES


def test_svg_is_byte_identical_across_runs(tmp_path: Path) -> None:
    """The determinism property, at the unit level: the same store spells the
    same SVG twice — coordinates, colours, element order and all. The overlay
    is in play too, so the colouring is held to the same standard."""
    texts = []
    for name in ("first", "second"):
        design = _laid_out(CLEAN, tmp_path / name)
        texts.append(_picture(design, tmp_path / name).render_svg(overlay_colours("state", design)))

    assert texts[0] == texts[1]


def test_svg_is_valid_xml_with_a_box_per_node(tmp_path: Path) -> None:
    design = _laid_out(CLEAN, tmp_path / "store")

    root = ET.fromstring(_picture(design, tmp_path / "store").render_svg())

    assert root.tag == f"{SVG}svg"
    boxes = [rect for rect in root.iter(f"{SVG}rect") if rect.get("data-ref")]
    assert {rect.get("data-ref") for rect in boxes} == CLEAN_NODES
    assert all(rect.get("fill") for rect in boxes)


def test_mermaid_starts_with_the_diagram_keyword_and_spells_the_edges(
    tmp_path: Path,
) -> None:
    design = _laid_out(CLEAN, tmp_path / "store")

    text = _picture(design, tmp_path / "store").render_mermaid()

    assert text.startswith("graph TD")
    assert "component_orders -->|contains| component_catalog" in text
    assert "component_orders -->|provides| seam_order_events" in text
    assert "component_cancellation -->|consumes| seam_order_events" in text


def test_mermaid_with_an_overlay_styles_by_class(tmp_path: Path) -> None:
    """The shared emitter still spells nodes and edges; the overlay adds
    ``classDef``/``class`` lines grouping the nodes by their class."""
    design = _laid_out(CLEAN, tmp_path / "store")

    text = _picture(design, tmp_path / "store").render_mermaid(overlay_colours("state", design))

    assert "classDef constrained fill:#" in text
    assert "classDef specified fill:#" in text
    assert "class component_cancellation constrained" in text
    assert "class component_catalog,component_orders,seam_order_events specified" in text


def test_d2_spells_boxes_and_edges(tmp_path: Path) -> None:
    design = _laid_out(CLEAN, tmp_path / "store")

    text = _picture(design, tmp_path / "store").render_d2()

    assert text.startswith("direction: right")
    assert 'component_orders: "Orders" {' in text
    assert "component_orders -> component_catalog: contains" in text
    assert "component_cancellation -> seam_order_events: consumes" in text


@pytest.mark.parametrize("fixture", ["clean", "brownfield", "composite"])
@pytest.mark.parametrize("fmt", ["svg", "mermaid", "d2"])
def test_each_format_is_snapshotted_per_fixture(
    tmp_path: Path, fixture: str, fmt: str, snapshot: SnapshotAssertion
) -> None:
    """One snapshot per fixture per format — the spec's own test shape. No
    overlay: the plain diagram is the bytes every overlay starts from."""
    design = _laid_out(FIXTURES / fixture, tmp_path / "store")

    assert RENDERERS[fmt](_picture(design, tmp_path / "store")) == snapshot


# --- pinned positions or refusal --------------------------------------------------


def test_no_layout_yaml_is_refused_pointing_at_ab_layout(tmp_path: Path) -> None:
    """No positions at all is the same refusal as some missing: the message
    names the command that pins them, never a silent fallback to auto-layout."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    design = resolve(load_store(store))

    with pytest.raises(LayoutError, match="ab layout"):
        _picture(design, store)


def test_a_missing_position_is_refused_rather_than_autolaid_out(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    design = resolve(load_store(store))
    full = compute(design)
    unpinned = Layout(positions=tuple(p for p in full.positions if p.ref != "seam:order-events"))
    write_layout(store, unpinned)

    with pytest.raises(LayoutError, match=r"seam:order-events.*ab layout"):
        _picture(design, store)


# --- the overlays -----------------------------------------------------------------


def test_state_overlay_colours_by_element_state(tmp_path: Path) -> None:
    """``clean/`` holds a ``constrained`` component next to ``specified``
    ones: their fills must differ, and the class is spelled on the box."""
    design = _laid_out(CLEAN, tmp_path / "store")

    colouring = overlay_colours("state", design)

    assert colouring.caption["component:cancellation"] == "constrained"
    assert colouring.caption["component:orders"] == "specified"
    assert colouring.fill["component:cancellation"] != colouring.fill["component:orders"]


def test_milestone_overlay_colours_scope_membership(tmp_path: Path) -> None:
    """``milestone:m1`` scopes exactly ``component:cancellation``: a member
    wears the milestone's colour, everything else stays neutral."""
    design = _laid_out(CLEAN, tmp_path / "store")

    colouring = overlay_colours("milestone", design)

    assert colouring.caption["component:cancellation"] == "milestone:m1"
    assert colouring.caption["component:orders"] == "in no milestone"
    assert colouring.fill["component:cancellation"] != colouring.fill["component:orders"]


def test_coverage_overlay_colours_implemented_elements(tmp_path: Path) -> None:
    """``composite/`` is the fixture with an implementation side: both
    components carry ``implemented_by``, the seam carries no ``verified_by``."""
    design = _laid_out(COMPOSITE, tmp_path / "store")

    colouring = overlay_colours("coverage", design)

    assert colouring.caption["component:billing-worker"] == "covered"
    assert colouring.caption["seam:invoice-events"] == "not covered"
    assert colouring.fill["component:billing-worker"] != colouring.fill["seam:invoice-events"]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def test_churn_overlay_reads_the_enclosing_repository_history(tmp_path: Path) -> None:
    """One element committed once, one committed three times: the buckets
    differ. Built in a throwaway repository so the answer is this test's own
    data, not whatever this checkout's history happens to say."""
    repo = tmp_path / "repo"
    store = repo / ".absicht"
    (store / "components").mkdir(parents=True)
    (store / "system.yaml").write_text("id: system:churn\ntitle: Churn\n", encoding="utf-8")

    def component(slug: str) -> str:
        return f"---\nid: component:{slug}\ntitle: {slug}\nstate: specified\n---\n"

    stable = store / "components" / "stable.md"
    fresh = store / "components" / "fresh.md"
    stable.write_text(component("stable"), encoding="utf-8")
    fresh.write_text(component("fresh"), encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "tests@absicht.invalid")
    _git(repo, "config", "user.name", "absicht tests")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c1")
    for count in (2, 3):
        # The body is carried verbatim, so an edit there changes the file git
        # counts without touching what the loader reads.
        stable.write_text(component("stable") + f"edit {count}\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", f"c{count}")

    design = resolve(load_store(store))
    write_layout(store, compute(design))

    colouring = overlay_colours("churn", design, root=store)

    assert colouring.caption["component:stable"] == "2+ changes"
    assert colouring.caption["component:fresh"] == "1 change"
    assert colouring.fill["component:stable"] != colouring.fill["component:fresh"]


def test_churn_outside_a_repository_is_zero_changes_not_an_error(tmp_path: Path) -> None:
    """A store need not live in a repository; with no history to read the
    overlay degenerates to one bucket rather than refusing to colour."""
    design = _laid_out(CLEAN, tmp_path / "store")

    colouring = overlay_colours("churn", design, root=tmp_path / "store")

    assert set(colouring.caption.values()) == {"0 changes"}


def test_an_unknown_overlay_name_is_a_programming_error(tmp_path: Path) -> None:
    design = _laid_out(CLEAN, tmp_path / "store")

    with pytest.raises(ValueError, match="no such overlay"):
        overlay_colours("weather", design)


# --- scope --------------------------------------------------------------------------


def test_scope_limits_nodes_and_edges_to_the_subtree(tmp_path: Path) -> None:
    """``component:catalog`` points at nothing: the smallest diagram that is
    still a diagram — one box, no arrows."""
    design = _laid_out(CLEAN, tmp_path / "store")

    picture = _picture(design, tmp_path / "store", scope="component:catalog")

    assert [element.id for element in picture.nodes] == ["component:catalog"]
    assert picture.edges == ()


def test_scope_does_not_demand_positions_for_out_of_scope_nodes(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    design = resolve(load_store(store))
    write_layout(
        store,
        Layout(positions=(Position(ref="component:catalog", x=0.0, y=0.0),)),
    )

    picture = _picture(design, store, scope="component:catalog")

    assert picture.positions["component:catalog"].x == 0.0


def test_an_unknown_scope_ref_raises_rather_than_scoping_everything(
    tmp_path: Path,
) -> None:
    design = _laid_out(CLEAN, tmp_path / "store")

    with pytest.raises(UnknownRefError, match="component:ghost"):
        _picture(design, tmp_path / "store", scope="component:ghost")
