"""``absicht.load``: walk a store into raw per-kind tuples, tolerating bad files.

The fixtures under ``tests/fixtures/systems/`` are the shared test data; what
these tests pin are the decisions the format leaves to the walk:

- a store with one broken file loads everything else and reports that file as
  one ``LoadError`` whose message names what is wrong — `check` turns it into
  a finding, `build` skips the element, neither crashes;
- a missing or unparsable ``design.yaml`` is one ``LoadError`` and a ``None``
  header, not a refusal: `load` returns what it could read, and refusing to
  fold a headerless store is `resolve`'s job one layer up;
- an element's outgoing edges are authored in its own file and collected into
  the one ``relationships`` tuple, in the order the walk read the elements —
  the store keeps an edge beside its owner, the model keeps it in one list,
  and this walk is where the two meet;
- within a kind directory only ``*.md`` files are elements, in sorted filename
  order, kinds in `Design` field order — determinism downstream starts here;
- ``resolve_store`` implements the store-location modes: a directory is the
  store, a ``.absicht`` marker file names it, and a remote ``design:`` target
  is refused clearly rather than half-fetched.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from absicht.codec import ASSEMBLED, dump_singleton
from absicht.load import (
    FileSource,
    LoadError,
    LoadErrorReason,
    StoreResolutionError,
    WorkingTree,
    load_store,
    resolve_store,
)
from absicht.models.design import State
from absicht.models.marker import Marker

FIXTURES = Path(__file__).parent / "fixtures" / "systems"

# What each fixture must load to. Only the collections a store populates are
# listed; every other one must come back empty, which the counts test enforces
# by walking `ASSEMBLED` and defaulting to zero. `broken`'s three failures are
# asserted by name in their own test.
EXPECTED: dict[str, dict[str, int]] = {
    "clean": {
        "glossary": 1,
        "actors": 1,
        "goals": 1,
        "requirements": 2,
        "qualities": 1,
        "constraints": 1,
        "behaviors": 4,
        "components": 4,
        "interfaces": 1,
        "data_entities": 1,
        "resources": 2,
        "libraries": 1,
        "decisions": 1,
        "milestones": 1,
        "relationships": 12,
    },
    "brownfield": {
        "goals": 1,
        "requirements": 2,
        "behaviors": 1,
        "components": 3,
        "data_entities": 1,
        "external_services": 1,
        "questions": 2,
        "milestones": 1,
        "notes": 1,
        "relationships": 4,
    },
    "broken": {
        "goals": 1,
        "requirements": 1,
        "behaviors": 7,
        "components": 7,
        "interfaces": 1,
        "resources": 1,
        "external_services": 1,
        "decisions": 1,
        "questions": 1,
        "milestones": 1,
        "relationships": 4,
    },
    "composite": {
        "goals": 1,
        "requirements": 1,
        "behaviors": 1,
        "components": 3,
        "interfaces": 1,
        "data_entities": 1,
        "external_services": 1,
        "milestones": 1,
        "relationships": 5,
    },
}

EXPECTED_ERRORS = {"clean": 0, "brownfield": 0, "broken": 3, "composite": 0}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_fixture_loads_to_its_expected_counts(name: str) -> None:
    loaded = load_store(FIXTURES / name)

    for collection, count in ((c, EXPECTED[name].get(c, 0)) for c in ASSEMBLED):
        assert len(getattr(loaded, collection)) == count, collection
    assert len(loaded.errors) == EXPECTED_ERRORS[name]
    assert loaded.header is not None


def test_broken_reports_its_three_parse_failures_by_name() -> None:
    """The walk continues past a bad file, and each error says what is wrong
    with which path — never a stack trace for `check` to lift into a finding.
    Both behavior files are refused by the records' own validators at parse
    time, so they surface here, at the load layer, like the YAML one."""

    (garbage, bad_anchor, bad_timing) = load_store(FIXTURES / "broken").errors

    assert garbage.path == "requirements/garbage.md"
    assert "invalid YAML" in garbage.message
    assert garbage.reason is LoadErrorReason.SYNTAX
    assert bad_anchor.path == "behaviors/bad-anchor.md"
    assert "not anchored to 'behavior:bad-anchor'" in bad_anchor.message
    assert bad_anchor.reason is LoadErrorReason.VALIDATION
    assert bad_timing.path == "behaviors/bad-timing.md"
    assert "`must_not` means at no point: omit `timing`" in bad_timing.message
    assert bad_timing.reason is LoadErrorReason.VALIDATION


def test_broken_parses_its_check_layer_defects_without_flagging_them() -> None:
    """The rest of `broken/`'s defects are invalid *designs*, not broken
    files: each loads without a `LoadError`, carrying the shape the check
    layer exists to judge — a nesting cycle and an `unknown` nobody owns."""

    loaded = load_store(FIXTURES / "broken")

    components = {component.id: component for component in loaded.components}
    assert components["component:loop-a"].parent == "component:loop-b"
    assert components["component:loop-b"].parent == "component:loop-a"
    (question,) = loaded.questions
    assert question.id == "question:unowned-unknown"
    assert question.state is State.UNKNOWN
    assert question.owner is None


# ----------------------------------------------------------- relationships


def test_every_relates_block_lands_in_one_list_in_walk_order() -> None:
    """The store spreads the edges over the files that own them; the model
    wants them in one list. The walk is the join, and its order is the walk's
    own — kinds in `Design` field order, files sorted within a kind — because
    `build` is byte-stable and that starts here."""

    loaded = load_store(FIXTURES / "clean")

    assert [(edge.source_id, edge.type.value, edge.target_id) for edge in loaded.relationships] == [
        ("req:browse-catalog", "derives_from", "goal:cheap-orders"),
        ("req:cancel-orders", "derives_from", "goal:cheap-orders"),
        ("behavior:catalog-browsable", "realizes", "req:browse-catalog"),
        ("behavior:order-cancelled", "realizes", "req:cancel-orders"),
        ("component:cancellation", "calls", "interface:order-events"),
        ("component:cancellation", "satisfies", "quality:cancel-latency"),
        ("component:catalog", "implements", "req:browse-catalog"),
        ("component:orders", "implements", "req:cancel-orders"),
        ("component:orders", "constrained_by", "constraint:gdpr-erasure"),
        ("component:orders", "depends_on", "library:pydantic"),
        ("component:orders", "depends_on", "resource:order-cache"),
        ("component:orders", "depends_on", "resource:order-stream"),
    ]


def test_an_edges_label_and_technology_survive_the_walk() -> None:
    """The two fields that make an edge drawable: without them a C4 arrow
    would have to be reconstructed from the two elements it joins, and it
    cannot be."""

    loaded = load_store(FIXTURES / "clean")

    (edge,) = [e for e in loaded.relationships if e.target_id == "interface:order-events"]
    assert edge.description == "publishes the cancellation"
    assert edge.technology == "JSON over the event bus"


def test_a_file_with_a_broken_relates_block_is_one_load_error(tmp_path: Path) -> None:
    """An edge is part of its element's file, so a malformed one costs that
    element and nothing else: the tolerance contract does not stop at the
    front matter's own fields."""

    _write(tmp_path, "design.yaml", _DESIGN)
    _write(tmp_path, "components/bad.md", _component("component:bad", "Bad", "relates: nope\n"))
    _write(tmp_path, "components/kept.md", _component("component:kept", "Kept"))

    loaded = load_store(tmp_path)

    assert [component.id for component in loaded.components] == ["component:kept"]
    assert loaded.relationships == ()
    assert loaded.errors[0].path == "components/bad.md"
    assert loaded.errors[0].reason is LoadErrorReason.SYNTAX


# ----------------------------------------------------------------- header


def test_a_store_without_design_yaml_still_loads_its_elements(tmp_path: Path) -> None:
    _write(tmp_path, "components/kept.md", _component("component:kept", "Kept"))

    loaded = load_store(tmp_path)

    assert loaded.header is None
    assert [component.id for component in loaded.components] == ["component:kept"]
    assert loaded.errors == (
        LoadError(
            path="design.yaml", message=_DESIGN_MISSING, reason=LoadErrorReason.MISSING_DESIGN
        ),
    )


def test_an_unparsable_design_yaml_is_one_error_and_a_none_header(tmp_path: Path) -> None:
    _write(tmp_path, "design.yaml", "id: [unclosed\n")

    loaded = load_store(tmp_path)

    assert loaded.header is None
    assert loaded.errors[0].path == "design.yaml"
    assert "invalid YAML" in loaded.errors[0].message
    assert loaded.errors[0].reason is LoadErrorReason.SYNTAX


# ------------------------------------------------------------------- walk


def test_elements_load_in_sorted_filename_order(tmp_path: Path) -> None:
    _write(tmp_path, "design.yaml", _DESIGN)
    for slug in ("zeta", "alpha", "mid"):
        _write(tmp_path, f"components/{slug}.md", _component(f"component:{slug}", slug))

    assert [component.id for component in load_store(tmp_path).components] == [
        "component:alpha",
        "component:mid",
        "component:zeta",
    ]


def test_only_markdown_files_in_a_kind_directory_are_elements(tmp_path: Path) -> None:
    """A `.gitkeep` holding an empty directory in git is not an element and not
    an error; an element is a `<slug>.md` file."""

    _write(tmp_path, "design.yaml", _DESIGN)
    _write(tmp_path, "components/real.md", _component("component:real", "Real"))
    _write(tmp_path, "components/.gitkeep", "")

    loaded = load_store(tmp_path)

    assert [component.id for component in loaded.components] == ["component:real"]
    assert loaded.errors == ()


def test_an_unreadable_file_is_a_load_error_not_a_crash(tmp_path: Path) -> None:
    """Tolerance covers the operating system too: a file that cannot be read
    is reported like one that cannot be parsed. Served through a custom
    `FileSource`, which is also the seam `absicht.git` implements."""

    _write(tmp_path, "design.yaml", _DESIGN)
    _write(tmp_path, "components/locked.md", _component("component:locked", "Locked"))

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


# ------------------------------------------------------------------ notes


def test_notes_load_into_their_own_collection() -> None:
    """`notes/` is walked like a kind directory, into a collection the
    `Design` never sees: notes are committed store contents and not elements,
    which is why the tuple sits on `LoadedStore` beside — never inside — the
    element kinds."""

    loaded = load_store(FIXTURES / "brownfield")

    (note,) = loaded.notes
    assert note.id == "note:a1b2c3"
    assert note.created_on == date(2026, 2, 11)
    assert note.about == ("component:shadow-report",)
    assert note.text.startswith("Ask ops")
    assert loaded.errors == ()


def test_a_broken_note_file_is_one_load_error_like_any_other(tmp_path: Path) -> None:
    """The tolerance contract covers `notes/` too: one bad file is a finding
    for `ab check`, never a reason to lose the rest of the inbox."""

    _write(tmp_path, "design.yaml", _DESIGN)
    _write(
        tmp_path,
        "notes/bad.md",
        "---\nid: note:bad123\ncreated_on: 2026-08-01\nabout: not a ref\n---\n",
    )
    _write(tmp_path, "notes/kept.md", "---\nid: note:kept12\ncreated_on: 2026-08-01\n---\nKept.\n")

    loaded = load_store(tmp_path)

    assert [note.id for note in loaded.notes] == ["note:kept12"]
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
    """Fetching is future work; half-implementing one would fail silently
    somewhere else, so it is refused up front."""

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


_DESIGN = "id: design:tiny\ntitle: Tiny\nversion: 0.1.0\n"
_DESIGN_MISSING = "design.yaml is missing: a store is a design, and a design has an id"


def _component(ref: str, title: str, extra: str = "") -> str:
    return f"---\nid: {ref}\ntitle: {title}\nlevel: container\n{extra}---\n"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
