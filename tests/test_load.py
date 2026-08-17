"""``absicht.load``: walk a store into raw per-kind tuples, tolerating bad files.

The fixtures under ``tests/fixtures/systems/`` are the shared test data
(``docs/tasks/00-conventions.md``, *Fixtures*); what these tests pin are the
decisions the spec leaves to the implementation:

- a store with one broken file loads everything else and reports the file as
  one ``LoadError`` whose message names what is wrong — `check` turns that
  into a finding, `build` skips the element, neither crashes;
- a missing or unparsable ``system.yaml`` is one ``LoadError`` and
  ``system is None``, not a refusal: `load` returns what it could read, and
  refusing to fold a systemless store is `build`'s job;
- within a kind directory only ``*.md`` files are elements, in sorted filename
  order, kinds in `Design` field order — determinism downstream starts here;
- ``resolve_store`` implements the store-location modes from ``cli.md``'s
  global flags table: a directory is the store, a `.absicht` marker file names
  it, and a remote ``design:`` target is refused clearly rather than
  half-fetched.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from absicht.codec import dump_singleton
from absicht.load import (
    FileSource,
    LoadError,
    LoadErrorReason,
    StoreResolutionError,
    WorkingTree,
    load_store,
    resolve_store,
)
from absicht.models import Marker, State

FIXTURES = Path(__file__).parent / "fixtures" / "systems"

# What each fixture must load to: elements per kind, plus how many files fail
# on the way. `broken`'s three failures are asserted by name in their own test.
EXPECTED: dict[str, dict[str, int]] = {
    "clean": {
        "externals": 0,
        "requirements": 2,
        "non_functionals": 0,
        "stories": 1,
        "components": 3,
        "seams": 1,
        "data": 1,
        "resources": 1,
        "behaviors": 2,
        "decisions": 1,
        "rejections": 0,
        "questions": 0,
        "milestones": 1,
        "errors": 0,
    },
    "brownfield": {
        "externals": 1,
        "requirements": 1,
        "non_functionals": 0,
        "stories": 1,
        "components": 2,
        "seams": 0,
        "data": 1,
        "resources": 0,
        "behaviors": 1,
        "decisions": 0,
        "rejections": 0,
        "questions": 2,
        "milestones": 1,
        "errors": 0,
    },
    "broken": {
        "externals": 1,
        "requirements": 0,
        "non_functionals": 0,
        "stories": 1,
        "components": 3,
        "seams": 1,
        "data": 0,
        "resources": 1,
        "behaviors": 4,
        "decisions": 1,
        "rejections": 0,
        "questions": 1,
        "milestones": 0,
        "errors": 3,
    },
    "composite": {
        "externals": 1,
        "requirements": 0,
        "non_functionals": 0,
        "stories": 0,
        "components": 2,
        "seams": 1,
        "data": 1,
        "resources": 0,
        "behaviors": 0,
        "decisions": 0,
        "rejections": 0,
        "questions": 0,
        "milestones": 0,
        "errors": 0,
    },
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_fixture_loads_to_its_expected_counts(name: str) -> None:
    loaded = load_store(FIXTURES / name)

    for kind, count in EXPECTED[name].items():
        assert len(getattr(loaded, kind)) == count, kind
    assert loaded.system is not None


def test_broken_reports_its_three_parse_failures_by_name() -> None:
    """The walk continues past a bad file, and each error says what is wrong
    with which path — never a stack trace for `check` to lift into a finding.
    A broken behavior file is one finding among the rest, not a crash: the
    `must_not`-with-`timing` shape is refused by `Observation`'s own validator
    at parse time, so it surfaces here, at the load layer, like the others."""

    (garbage, bad_anchor, bad_timing) = load_store(FIXTURES / "broken").errors

    assert garbage.path == "requirements/garbage.md"
    assert "invalid YAML" in garbage.message
    assert garbage.reason is LoadErrorReason.SYNTAX
    assert bad_anchor.path == "stories/bad-anchor.md"
    assert "not anchored to 'story:bad-anchor'" in bad_anchor.message
    assert bad_anchor.reason is LoadErrorReason.VALIDATION
    assert bad_timing.path == "behaviors/bad-timing.md"
    assert "`must_not` means at no point: omit `timing`" in bad_timing.message
    assert bad_timing.reason is LoadErrorReason.VALIDATION


def test_broken_parses_its_check_layer_defects_without_flagging_them() -> None:
    """The remaining defects are deliberately invalid *designs*, not broken
    files: each loads without a `LoadError`, carrying the shape the check
    layer exists to judge — a `contains` cycle and an `unknown` nobody owns
    (`06-fixtures.md`: one clearly-named case per failure family, so a later
    `check` task can point a rule at exactly the case that trips it)."""

    loaded = load_store(FIXTURES / "broken")

    components = {c.id: c for c in loaded.components}
    assert components["component:loop-a"].contains == ("component:loop-b",)
    assert components["component:loop-b"].contains == ("component:loop-a",)
    (question,) = loaded.questions
    assert question.id == "question:unowned-unknown"
    assert question.state is State.UNKNOWN
    assert question.owner is None


def test_a_store_without_system_yaml_still_loads_its_elements(tmp_path: Path) -> None:
    _write(tmp_path, "components/kept.md", _element("component:kept", "Kept"))

    loaded = load_store(tmp_path)

    assert loaded.system is None
    assert [c.id for c in loaded.components] == ["component:kept"]
    assert loaded.errors == (
        LoadError(
            path="system.yaml", message=_SYSTEM_MISSING, reason=LoadErrorReason.MISSING_SYSTEM
        ),
    )


def test_an_unparsable_system_yaml_is_one_error_and_a_none_system(tmp_path: Path) -> None:
    _write(tmp_path, "system.yaml", "id: [unclosed\n")

    loaded = load_store(tmp_path)

    assert loaded.system is None
    assert loaded.errors[0].path == "system.yaml"
    assert "invalid YAML" in loaded.errors[0].message


def test_elements_load_in_sorted_filename_order(tmp_path: Path) -> None:
    _write(tmp_path, "system.yaml", _SYSTEM)
    for slug in ("zeta", "alpha", "mid"):
        _write(tmp_path, f"components/{slug}.md", _element(f"component:{slug}", slug))

    assert [c.id for c in load_store(tmp_path).components] == [
        "component:alpha",
        "component:mid",
        "component:zeta",
    ]


def test_only_markdown_files_in_a_kind_directory_are_elements(tmp_path: Path) -> None:
    """A `.gitkeep` holding an empty directory in git is not an element and not
    an error; `00-conventions.md` spells elements as `<slug>.md` files."""

    _write(tmp_path, "system.yaml", _SYSTEM)
    _write(tmp_path, "components/real.md", _element("component:real", "Real"))
    _write(tmp_path, "components/.gitkeep", "")

    loaded = load_store(tmp_path)

    assert [c.id for c in loaded.components] == ["component:real"]
    assert loaded.errors == ()


def test_an_unreadable_file_is_a_load_error_not_a_crash(tmp_path: Path) -> None:
    """Tolerance covers the operating system too: a file that cannot be read
    is reported like one that cannot be parsed. Served through a custom
    `FileSource`, which is also the seam `absicht.git` will implement."""

    _write(tmp_path, "system.yaml", _SYSTEM)
    _write(tmp_path, "components/locked.md", _element("component:locked", "Locked"))

    class _LockedFile(WorkingTree):
        def read_text(self, path: Path) -> str:
            if path.name == "locked.md":
                raise OSError("permission denied")
            return super().read_text(path)

    source: FileSource = _LockedFile()
    loaded = load_store(tmp_path, source=source)

    assert loaded.components == ()
    assert loaded.errors == (
        LoadError(
            path="components/locked.md", message="permission denied", reason=LoadErrorReason.IO
        ),
    )


# ----------------------------------------------------------------- notes


def test_notes_load_into_their_own_collection(tmp_path: Path) -> None:
    """`notes/` is walked like a kind directory, but into a collection the
    `Design` never sees: notes are committed store contents and not elements
    (docs/tasks/50-addendum-conventions.md), which is why the tuple lives on
    `LoadedStore` beside — never inside — the element kinds."""

    _write(tmp_path, "system.yaml", _SYSTEM)
    _write(
        tmp_path,
        "notes/stuck.md",
        "---\nid: note:stuck1\ncreated: 2026-08-01\npromoted_to: question:retention\n---\n"
        "What this became.\n",
    )
    _write(
        tmp_path, "notes/loose.md", "---\nid: note:loose1\ncreated: 2026-08-02\n---\nA thought.\n"
    )

    loaded = load_store(tmp_path)

    assert [n.id for n in loaded.notes] == ["note:loose1", "note:stuck1"]
    assert loaded.notes[0].created == date(2026, 8, 2)
    assert loaded.notes[1].promoted_to == "question:retention"
    assert loaded.errors == ()


def test_a_broken_note_file_is_one_load_error_like_any_other(tmp_path: Path) -> None:
    """The tolerance contract covers `notes/` too: one bad file is a finding
    for `ab check`, never a reason to lose the rest of the inbox."""

    _write(tmp_path, "system.yaml", _SYSTEM)
    _write(
        tmp_path, "notes/bad.md", "---\nid: note:bad123\ncreated: 2026-08-01\nref: not a ref\n---\n"
    )
    _write(tmp_path, "notes/kept.md", "---\nid: note:kept12\ncreated: 2026-08-01\n---\nKept.\n")

    loaded = load_store(tmp_path)

    assert [n.id for n in loaded.notes] == ["note:kept12"]
    assert len(loaded.errors) == 1
    assert loaded.errors[0].path == "notes/bad.md"
    assert loaded.errors[0].reason is LoadErrorReason.VALIDATION


# ------------------------------------------------------- store location modes


def _marker(path: Path, design: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_singleton(Marker(design=design)), encoding="utf-8")
    return path


def test_an_embedded_store_directory_resolves_to_itself(tmp_path: Path) -> None:
    store = tmp_path / ".absicht"
    store.mkdir()

    assert resolve_store(store) == store


def test_a_reference_marker_resolves_to_the_store_it_names(tmp_path: Path) -> None:
    store = tmp_path / "design"
    store.mkdir()
    marker = _marker(tmp_path / ".absicht", design=str(store))

    assert resolve_store(marker) == store


def test_a_relative_design_resolves_against_the_markers_directory(tmp_path: Path) -> None:
    """Relative to the marker, not the caller's cwd, so a marker and the store
    it names travel together."""

    store = tmp_path / "design"
    store.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    marker = _marker(repo / ".absicht", design="../design")

    assert resolve_store(marker) == store


@pytest.mark.parametrize(
    "design",
    ["https://design.example/acme.git", "git@github.com:acme/design.git"],
)
def test_a_remote_design_target_is_refused_clearly(tmp_path: Path, design: str) -> None:
    """Fetching is future work (`ab extract` territory); half-implementing a
    fetch would fail silently somewhere else, so it is refused up front."""

    marker = _marker(tmp_path / ".absicht", design=design)

    with pytest.raises(StoreResolutionError, match="not supported yet"):
        resolve_store(marker)


def test_a_design_target_that_does_not_exist_is_no_store(tmp_path: Path) -> None:
    marker = _marker(tmp_path / ".absicht", design=str(tmp_path / "nowhere"))

    with pytest.raises(StoreResolutionError, match="nowhere"):
        resolve_store(marker)


def test_a_path_that_is_neither_store_nor_marker_is_no_store(tmp_path: Path) -> None:
    with pytest.raises(StoreResolutionError, match="no store"):
        resolve_store(tmp_path / ".absicht")


def test_an_unparsable_marker_is_a_resolution_error(tmp_path: Path) -> None:
    """Written as raw text, not through `dump_singleton`: the point is a marker
    that does not parse, and a round trip would launder it into a valid one."""

    marker = tmp_path / ".absicht"
    marker.write_text("design: [unclosed\n", encoding="utf-8")

    with pytest.raises(StoreResolutionError, match=r"not a readable \.absicht marker"):
        resolve_store(marker)


def test_the_store_from_the_environment_goes_through_mode_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`$ABSICHT_STORE` names the same kind of path `--store` does, so it can
    be a marker file too — the mode detection must not be a default-only path.
    """

    store = tmp_path / "design"
    store.mkdir()
    marker = _marker(tmp_path / ".absicht", design=str(store))
    monkeypatch.setenv("ABSICHT_STORE", str(marker))

    assert resolve_store(Path(os.environ["ABSICHT_STORE"])) == store


# ----------------------------------------------------------------- helpers


_SYSTEM = "id: system:tiny\ntitle: Tiny\n"
_SYSTEM_MISSING = "system.yaml is missing: a store needs exactly one System element"


def _element(ref: str, title: str) -> str:
    return f"---\nid: {ref}\ntitle: {title}\n---\n"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
