"""``ab layout``: deterministic positions, pinned in ``layout.yaml``.

What these tests pin, per ``docs/tasks/25-layout.md``:

- the property the command exists for: two runs over the same store with the
  same ``--seed`` write byte-identical ``layout.yaml`` files — and a
  different ``--seed`` really does move something, so the flag is not
  decorative;
- the node set is the one ``docs/tasks/27-render-diagrams.md`` draws —
  components, interfaces and external services, plus the resources
  ``docs/tasks/60-addendum-render.md`` adds at the boundary, never every
  element — with the layered shape: a nested component ranks below its
  parent, interfaces below every component, resources below the external
  services;
- ``--recompute`` (the default behaviour) only fills gaps: positions an
  earlier run pinned survive a new element verbatim, which is what "stable
  layout" means in practice;
- ``--recompute-all`` discards the pinned values;
- ``--check`` is read-only: it names exactly the elements without a position
  and exits ``FINDINGS`` — a statement about the store, the same verdict a
  hand-broken ``layout.yaml`` earns, never a silent reset to empty;
- contradictory flag pairs are ``USAGE``.

Every writing case runs against a private copy of ``clean/``, like
``tests/test_migrate.py``: the command writes into the store it is pointed
at, and the shared fixtures stay pristine.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.layout import compute, read_layout
from absicht.models.design import (
    FORMAT_VERSION,
    Component,
    ComponentLevel,
    Design,
    ExternalService,
    Resource,
    ResourceKind,
)

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"

CLEAN_NODES = {
    "component:acme",
    "component:cancellation",
    "component:catalog",
    "component:orders",
    "interface:order-events",
    "resource:order-cache",
    "resource:order-stream",
}
"""Every diagram node in ``clean/``: four components, one interface and the two
resources the store depends on. No external services, and the prose kinds are
not diagram nodes — that boundary is itself under test."""

_NEW_COMPONENT = """---
id: component:new-thing
title: New thing
state: specified
level: container
---
"""


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """The clean fixture as a private copy under ``tmp_path``."""
    copied = tmp_path / "store"
    shutil.copytree(CLEAN, copied)
    return copied


def _positions(root: Path) -> dict[str, tuple[float, float]]:
    """``layout.yaml`` as a ref → coordinates mapping, read through the same
    codec the command writes with."""
    return {position.ref: (position.x, position.y) for position in read_layout(root).positions}


def _pin(root: Path, entries: dict[str, tuple[float, float]]) -> None:
    """Hand-author a ``layout.yaml`` in the spelling a human editing pinned
    positions would produce, so the input is independent of the writer the
    tests judge."""
    lines = ["positions:"]
    lines += [f"- ref: {ref}\n  x: {x}\n  y: {y}" for ref, (x, y) in entries.items()]
    (root / "layout.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_two_runs_with_the_same_seed_write_identical_files(store: Path, tmp_path: Path) -> None:
    other = tmp_path / "second"
    shutil.copytree(CLEAN, other)
    for target in (store, other):
        result = runner.invoke(app, ["--store", str(target), "layout", "--seed", "7"])
        assert result.exit_code == ExitCode.OK
    assert (store / "layout.yaml").read_bytes() == (other / "layout.yaml").read_bytes()


def test_a_different_seed_moves_the_boxes(store: Path, tmp_path: Path) -> None:
    other = tmp_path / "second"
    shutil.copytree(CLEAN, other)
    runner.invoke(app, ["--store", str(store), "layout", "--seed", "7"])
    runner.invoke(app, ["--store", str(other), "layout", "--seed", "8"])
    assert _positions(store) != _positions(other)


def test_positions_cover_exactly_the_diagram_kinds(store: Path) -> None:
    result = runner.invoke(app, ["--store", str(store), "layout"])

    assert result.exit_code == ExitCode.OK
    assert set(_positions(store)) == CLEAN_NODES


def test_the_layout_is_layered_children_below_parents_interfaces_below_components(
    store: Path,
) -> None:
    """``component:orders`` nests ``component:cancellation``; the interface sits
    under the components it connects. These two inequalities are the whole
    legibility claim of the algorithm — everything else is placement."""
    assert runner.invoke(app, ["--store", str(store), "layout"]).exit_code == ExitCode.OK
    positions = _positions(store)
    assert positions["component:cancellation"][1] > positions["component:orders"][1]
    deepest_component = max(y for ref, (_, y) in positions.items() if ref.startswith("component:"))
    assert positions["interface:order-events"][1] > deepest_component


@pytest.mark.parametrize("recompute", [[], ["--recompute"]], ids=["bare", "--recompute"])
def test_recompute_adds_only_the_new_elements(store: Path, recompute: list[str]) -> None:
    """A new component must not reshuffle the diagram: the positions an
    earlier run pinned survive verbatim and only the newcomer is placed —
    pinned by the bare invocation too, which is the default behaviour."""
    assert runner.invoke(app, ["--store", str(store), "layout"]).exit_code == ExitCode.OK
    before = _positions(store)
    (store / "components" / "new-thing.md").write_text(_NEW_COMPONENT, encoding="utf-8")

    result = runner.invoke(app, ["--store", str(store), "layout", *recompute])

    assert result.exit_code == ExitCode.OK
    after = _positions(store)
    assert set(after) == set(before) | {"component:new-thing"}
    assert {ref: after[ref] for ref in before} == before


def test_recompute_all_discards_the_pinned_positions(store: Path) -> None:
    pinned = {ref: (900.0 + index, 950.0) for index, ref in enumerate(sorted(CLEAN_NODES))}
    _pin(store, pinned)

    result = runner.invoke(app, ["--store", str(store), "layout", "--recompute-all"])

    assert result.exit_code == ExitCode.OK
    after = _positions(store)
    assert set(after) == CLEAN_NODES
    # "Recomputes", not "differs": none of the far-away hand-pinned values
    # survived, which a merge would have kept.
    assert set(after.values()).isdisjoint(set(pinned.values()))


def test_check_names_the_element_without_a_position(store: Path) -> None:
    covered, uncovered = sorted(CLEAN_NODES)[:-1], sorted(CLEAN_NODES)[-1]
    _pin(store, dict.fromkeys(covered, (1.0, 1.0)))

    result = runner.invoke(app, ["--store", str(store), "layout", "--check"])
    json_result = runner.invoke(app, ["--store", str(store), "layout", "--check", "--json"])

    assert result.exit_code == ExitCode.FINDINGS
    assert result.stdout == f"no position for {uncovered}\n"
    assert json_result.exit_code == ExitCode.FINDINGS
    assert json.loads(json_result.stdout)["missing"] == [uncovered]


def test_check_passes_when_every_element_is_positioned(store: Path) -> None:
    assert runner.invoke(app, ["--store", str(store), "layout"]).exit_code == ExitCode.OK

    result = runner.invoke(app, ["--store", str(store), "layout", "--check"])

    assert result.exit_code == ExitCode.OK
    assert result.stdout == f"every diagram element has a position ({len(CLEAN_NODES)})\n"


def test_an_unreadable_layout_yaml_is_findings_not_a_silent_reset(store: Path) -> None:
    """Reading positions as "nothing pinned yet" would throw away the data
    this command exists to keep, so a broken file is a finding about the
    store — for the write path no less than for ``--check``."""
    (store / "layout.yaml").write_text("positions: 42\n", encoding="utf-8")

    for argv in (["layout"], ["layout", "--check"]):
        result = runner.invoke(app, ["--store", str(store), *argv])

        assert result.exit_code == ExitCode.FINDINGS
        assert result.stdout == ""
        assert "layout.yaml" in result.stderr


@pytest.mark.parametrize(
    ("flags", "flag"),
    [
        (["--recompute", "--recompute-all"], "--recompute"),
        (["--check", "--recompute"], "--check"),
        (["--check", "--recompute-all"], "--check"),
    ],
)
def test_contradictory_flags_are_usage(store: Path, flags: list[str], flag: str) -> None:
    result = runner.invoke(app, ["--store", str(store), "layout", *flags])

    assert result.exit_code == ExitCode.USAGE
    assert flag in result.stderr
    assert result.stdout == ""


def test_json_envelopes_the_written_file(store: Path) -> None:
    result = runner.invoke(app, ["--store", str(store), "layout", "--json"])

    assert result.exit_code == ExitCode.OK
    document = json.loads(result.stdout)
    assert document["format_version"] == FORMAT_VERSION
    assert document["out"].endswith("layout.yaml")
    assert document["total"] == len(CLEAN_NODES)
    assert document["added"] == len(CLEAN_NODES)


def test_a_nesting_cycle_still_lays_out_deterministically() -> None:
    """``broken/`` cannot reach this command (its unreadable files are
    ``build``'s refusal), so the cycle case is a hand-built design: whatever
    the ``parent`` walk cannot reach from a root is appended in id order
    rather than hanging — placing a broken graph is layout's job, reporting
    it is ``check``'s."""
    design = Design(
        id="design:cycle",
        title="Cycle",
        version="0.1.0",
        components=(
            Component(
                id="component:loop-a",
                title="A",
                level=ComponentLevel.CONTAINER,
                parent="component:loop-b",
            ),
            Component(
                id="component:loop-b",
                title="B",
                level=ComponentLevel.CONTAINER,
                parent="component:loop-a",
            ),
        ),
    )

    positions = {
        position.ref: (position.x, position.y) for position in compute(design, seed=0).positions
    }

    assert set(positions) == {"component:loop-a", "component:loop-b"}
    assert positions["component:loop-a"] != positions["component:loop-b"]


def test_a_resource_in_the_store_gets_a_position_like_every_node(store: Path) -> None:
    """docs/tasks/60-addendum-render.md's own assert: `ab layout` handles the
    addendum's kinds generically — `clean/` ships a resource, and a bare
    invocation pins it with no flag, because the node set is one function."""
    result = runner.invoke(app, ["--store", str(store), "layout"])

    assert result.exit_code == ExitCode.OK
    assert "resource:order-cache" in _positions(store)


def test_resources_rank_below_the_external_services_at_the_boundary() -> None:
    """A resource is outside the design boundary (addendum §1), and the
    picture says so spatially: resources take the outermost rank, below the
    external services, which sit below the interfaces, which sit below every
    component."""
    design = Design(
        id="design:edge",
        title="Edge",
        version="0.1.0",
        components=(Component(id="component:core", title="Core", level=ComponentLevel.SYSTEM),),
        external_services=(ExternalService(id="external:payment-api", title="Payment API"),),
        resources=(
            Resource(
                id="resource:order-cache",
                title="Order cache",
                resource_kind=ResourceKind.STORE,
                technology="Redis",
            ),
        ),
    )

    positions = {
        position.ref: (position.x, position.y) for position in compute(design, seed=0).positions
    }

    assert positions["resource:order-cache"][1] > positions["external:payment-api"][1]
    assert positions["external:payment-api"][1] > positions["component:core"][1]
