"""``absicht.markers.sync``: the store's half of the discovery bargain.

What these tests pin, per docs/tasks/44-marker-sync.md:

- a fresh repo gets a marker whose units are the design's ``implemented_by``
  entries speaking for that repo, watermarks unset — nothing to preserve yet;
- an update preserves ``at``/``design_rev`` for units that survive (keyed by
  component id, so a repathed unit keeps its watermark and a surviving exact
  ``(id, path)`` pair keeps its own, not a sibling's), drops units no longer
  referenced and adds new ones with no watermark — sync never resets a
  watermark, advancing one is ``ab marker stamp``'s job;
- an entry's repo half names a repo by path suffix — the same rule ``ab
  verify`` maps changed files by — and an entry with no ``#`` is the
  single-repo spelling that speaks for every repo;
- a ``.absicht/`` directory (embedded mode) or an unreadable marker file is
  refused rather than converted or clobbered.

``check``, the read-only twin docs/tasks/45-marker-check.md specifies:

- a marker fresh from ``sync`` agrees with the store, and watermark drift —
  ``at``/``design_rev`` behind the design — is not a disagreement: how far
  behind a marker is ``ab status``'s subject, not a correctness problem;
- a unit the store gained or dropped, or a unit the marker carries at a
  path the store no longer names, is a finding;
- no marker at all, an embedded ``.absicht/`` directory or an unreadable
  file is refused, each in its own words.

``stamp``, the advancing hand docs/tasks/46-marker-stamp.md specifies:

- one unit's ``at``/``design_rev`` move — from whatever they already were,
  since moving an existing watermark is the point — and every other unit in
  the marker is untouched; a unit implemented at two paths is one unit, so
  both its watermarks move together;
- a unit the marker does not carry, or a repo with no marker at all, is
  refused in its own words: a stamp is a claim about a unit the store synced
  into the repo, never a way to widen the marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from absicht.codec import dump_singleton, parse_singleton
from absicht.findings import Severity
from absicht.markers import MarkerError, check, stamp, sync
from absicht.models import Component, Design, Marker, System, UnitWatermark


def _design(*components: Component) -> Design:
    return Design(system=System(id="system:tiny", title="Tiny"), components=components)


def _component(ref: str, *implemented_by: str) -> Component:
    return Component(id=ref, title=ref.removeprefix("component:"), implemented_by=implemented_by)


def _repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True)
    return repo


def test_a_fresh_repo_gets_the_entries_that_speak_for_it(tmp_path: Path) -> None:
    """The wrong repo's entry stays out even at the same path: the repo half,
    not the path, decides whose marker an entry lands in."""
    repo = _repo(tmp_path, "acme/core")
    design = _design(
        _component("component:core", "acme/core#src/core"),
        _component("component:elsewhere", "acme/other#src/core"),
    )

    marker = sync(design, repo, design_url="../design")

    assert marker == Marker(
        design="../design",
        units=(UnitWatermark(id="component:core", path="src/core"),),
    )
    assert parse_singleton((repo / ".absicht").read_text(encoding="utf-8"), model=Marker) == marker


def test_a_bare_entry_is_the_single_repo_spelling(tmp_path: Path) -> None:
    """No ``#`` names no repo, so the entry speaks for every repo — the same
    reading ``ab verify`` gives a bare path, which is why the two readers of
    ``implemented_by`` never disagree about whose code an entry names."""
    design = _design(_component("component:shared", "src/shared"))

    marker = sync(design, _repo(tmp_path, "anywhere"), design_url="../design")

    assert marker.units == (UnitWatermark(id="component:shared", path="src/shared"),)


def test_an_update_preserves_surviving_watermarks_drops_and_adds_units(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, "acme/r")
    sync(
        _design(
            _component("component:a", "acme/r#src/a", "acme/r#src/legacy"),
            _component("component:b", "acme/r#src/b"),
        ),
        repo,
        design_url="../design",
    )
    # The watermarks a landing commit stamped: one per (id, path) pair, each
    # distinct, so the assertions below can tell preservation from guesswork.
    (repo / ".absicht").write_text(
        dump_singleton(
            Marker(
                design="../design",
                units=(
                    UnitWatermark(
                        id="component:a", path="src/a", at="milestone:m1", design_rev="deadbeef"
                    ),
                    UnitWatermark(
                        id="component:a", path="src/legacy", at="milestone:m0", design_rev="older"
                    ),
                    UnitWatermark(
                        id="component:b", path="src/b", at="milestone:m2", design_rev="beefdead"
                    ),
                ),
            )
        ),
        encoding="utf-8",
    )

    marker = sync(
        _design(
            _component("component:a", "acme/r#src/a"),
            _component("component:c", "acme/r#src/c"),
        ),
        repo,
        design_url="../design",
    )

    assert marker.units == (
        # kept: `src/a`'s own watermark, not `src/legacy`'s
        UnitWatermark(id="component:a", path="src/a", at="milestone:m1", design_rev="deadbeef"),
        # added, with nothing to preserve
        UnitWatermark(id="component:c", path="src/c"),
    )


def test_a_repathed_unit_keeps_its_watermark(tmp_path: Path) -> None:
    """Sync repaths units as ``implemented_by`` moves; the watermark belongs
    to the unit (its id), not to the path it happens to sit at."""
    repo = _repo(tmp_path, "acme/r")
    sync(_design(_component("component:a", "acme/r#src/old")), repo, design_url="../design")
    (repo / ".absicht").write_text(
        dump_singleton(
            Marker(
                design="../design",
                units=(
                    UnitWatermark(
                        id="component:a", path="src/old", at="milestone:m1", design_rev="deadbeef"
                    ),
                ),
            )
        ),
        encoding="utf-8",
    )

    marker = sync(
        _design(_component("component:a", "acme/r#src/new")), repo, design_url="../design"
    )

    assert marker.units == (
        UnitWatermark(id="component:a", path="src/new", at="milestone:m1", design_rev="deadbeef"),
    )


def test_a_repo_no_entry_names_still_gets_a_truthful_empty_marker(tmp_path: Path) -> None:
    marker = sync(
        _design(_component("component:core", "acme/core#src/core")),
        _repo(tmp_path, "elsewhere"),
        design_url="../design",
    )

    assert marker == Marker(design="../design")
    assert (tmp_path / "elsewhere" / ".absicht").is_file()


def test_an_embedded_store_is_refused_not_converted(tmp_path: Path) -> None:
    """A `.absicht/` directory is embedded mode; sync never turns a store's
    own repo into a marker-holding one — the two modes are exclusive."""
    repo = _repo(tmp_path, "r")
    (repo / ".absicht").mkdir()

    with pytest.raises(MarkerError, match="directory"):
        sync(_design(), repo, design_url="../design")

    assert list((repo / ".absicht").iterdir()) == []


def test_an_unreadable_marker_is_refused_not_clobbered(tmp_path: Path) -> None:
    """Overwriting a marker sync cannot parse would drop watermarks nobody
    preserved; the file survives for a human to fix instead."""
    repo = _repo(tmp_path, "r")
    broken = repo / ".absicht"
    broken.write_text("design: [an unclosed\n", encoding="utf-8")

    with pytest.raises(MarkerError, match="not a readable"):
        sync(_design(), repo, design_url="../design")

    assert broken.read_text(encoding="utf-8") == "design: [an unclosed\n"


def test_a_repo_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MarkerError, match="no such directory"):
        sync(_design(), tmp_path / "nowhere", design_url="../design")


def test_a_marker_fresh_from_sync_agrees_with_the_store(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "acme/r")
    design = _design(_component("component:a", "acme/r#src/a"))
    sync(design, repo, design_url="../design")

    assert check(design, repo) == ()


def test_watermark_drift_is_not_a_marker_disagreement(tmp_path: Path) -> None:
    """How far a watermark is behind the design is `ab status`'s whole
    subject: `marker check` judges the marker's shape — which units, which
    paths — and never reads `at`/`design_rev`."""
    repo = _repo(tmp_path, "acme/r")
    design = _design(_component("component:a", "acme/r#src/a"))
    sync(design, repo, design_url="../design")
    (repo / ".absicht").write_text(
        dump_singleton(
            Marker(
                design="../design",
                units=(
                    UnitWatermark(
                        id="component:a", path="src/a", at="milestone:m0", design_rev="ancient"
                    ),
                ),
            )
        ),
        encoding="utf-8",
    )

    assert check(design, repo) == ()


def test_a_unit_the_store_gained_is_reported_missing(tmp_path: Path) -> None:
    """The spec's own simulation: sync, add an `implemented_by` entry, do
    not resync — the marker under-reports what the repo implements."""
    repo = _repo(tmp_path, "acme/r")
    sync(_design(_component("component:a", "acme/r#src/a")), repo, design_url="../design")

    (missing,) = check(_design(_component("component:a", "acme/r#src/a", "acme/r#src/new")), repo)

    assert missing.rule_id == "marker/missing-unit"
    assert missing.severity is Severity.ERROR
    assert missing.ref == "component:a"
    assert "src/new" in missing.message


def test_a_unit_the_store_dropped_is_reported_stray(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "acme/r")
    sync(
        _design(
            _component("component:a", "acme/r#src/a"),
            _component("component:b", "acme/r#src/b"),
        ),
        repo,
        design_url="../design",
    )

    (stray,) = check(_design(_component("component:a", "acme/r#src/a")), repo)

    assert stray.rule_id == "marker/stray-unit"
    assert stray.severity is Severity.ERROR
    assert stray.ref == "component:b"
    assert "src/b" in stray.message


def test_a_repathed_unit_is_reported_as_the_move_it_is(tmp_path: Path) -> None:
    """A component that moved is one finding about the move, not a missing
    unit plus a stray one saying the same thing twice."""
    repo = _repo(tmp_path, "acme/r")
    sync(_design(_component("component:a", "acme/r#src/old")), repo, design_url="../design")

    (moved,) = check(_design(_component("component:a", "acme/r#src/new")), repo)

    assert moved.rule_id == "marker/moved-unit"
    assert moved.severity is Severity.ERROR
    assert moved.ref == "component:a"
    assert "src/old" in moved.message
    assert "src/new" in moved.message


def test_a_repo_without_a_marker_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "r")

    with pytest.raises(MarkerError, match="no marker to check"):
        check(_design(), repo)


def test_an_embedded_repo_is_refused_for_checking_too(tmp_path: Path) -> None:
    """`marker check` on a store's own repo does not make sense either: an
    embedded `.absicht/` directory carries no marker file to compare."""
    repo = _repo(tmp_path, "r")
    (repo / ".absicht").mkdir()

    with pytest.raises(MarkerError, match="is a directory"):
        check(_design(), repo)


def test_an_unreadable_marker_is_refused_for_checking(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "r")
    (repo / ".absicht").write_text("design: [an unclosed\n", encoding="utf-8")

    with pytest.raises(MarkerError, match="not a readable"):
        check(_design(), repo)


def test_stamping_moves_one_unit_and_leaves_the_rest_alone(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "acme/r")
    # The state a first landing leaves behind: both units already stamped.
    (repo / ".absicht").write_text(
        dump_singleton(
            Marker(
                design="../design",
                units=(
                    UnitWatermark(
                        id="component:a", path="src/a", at="milestone:m0", design_rev="older"
                    ),
                    UnitWatermark(
                        id="component:b", path="src/b", at="milestone:m0", design_rev="beefdead"
                    ),
                ),
            )
        ),
        encoding="utf-8",
    )

    marker = stamp(repo, "component:a", "milestone:m1", design_rev="deadbeef")

    assert marker.units == (
        UnitWatermark(id="component:a", path="src/a", at="milestone:m1", design_rev="deadbeef"),
        # `b`'s watermark is not stamp's to move
        UnitWatermark(id="component:b", path="src/b", at="milestone:m0", design_rev="beefdead"),
    )
    assert parse_singleton((repo / ".absicht").read_text(encoding="utf-8"), model=Marker) == marker


def test_a_unit_implemented_at_two_paths_moves_as_one(tmp_path: Path) -> None:
    """Both watermarks describe the same code's progress; moving only one
    would leave `ab status` reading the stale half as the unit being behind."""
    repo = _repo(tmp_path, "acme/r")
    (repo / ".absicht").write_text(
        dump_singleton(
            Marker(
                design="../design",
                units=(
                    UnitWatermark(id="component:a", path="src/a"),
                    UnitWatermark(id="component:a", path="src/legacy"),
                ),
            )
        ),
        encoding="utf-8",
    )

    marker = stamp(repo, "component:a", "milestone:m1", design_rev="deadbeef")

    assert marker.units == (
        UnitWatermark(id="component:a", path="src/a", at="milestone:m1", design_rev="deadbeef"),
        UnitWatermark(
            id="component:a", path="src/legacy", at="milestone:m1", design_rev="deadbeef"
        ),
    )


def test_a_unit_the_marker_does_not_carry_is_refused_for_stamping(tmp_path: Path) -> None:
    """Widening the marker is `marker sync`'s job; a unit it never carried has
    no watermark to move."""
    repo = _repo(tmp_path, "acme/r")
    (repo / ".absicht").write_text(
        dump_singleton(
            Marker(design="../design", units=(UnitWatermark(id="component:a", path="src/a"),))
        ),
        encoding="utf-8",
    )

    with pytest.raises(MarkerError, match="no such unit"):
        stamp(repo, "component:elsewhere", "milestone:m1", design_rev="deadbeef")


def test_a_repo_without_a_marker_is_refused_for_stamping(tmp_path: Path) -> None:
    """Nothing to move: sync writes the marker, stamp only advances it."""
    repo = _repo(tmp_path, "acme/r")

    with pytest.raises(MarkerError, match="no marker to stamp"):
        stamp(repo, "component:a", "milestone:m1", design_rev="deadbeef")
