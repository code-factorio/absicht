"""Write a repo's `.absicht` marker from the design store, and hold it to
what the store says.

`ab marker sync` (docs/tasks/44-marker-sync.md) is the store's half of the
discovery bargain the README's Discovery section describes: the implementing
repo gets a regenerable hint naming where the design lives and which units
this repo implements, while the store stays authoritative. Two rules carry
the write half of the module:

- **Watermarks survive.** An update keeps `at`/`design_rev` for every unit
  the new marker still carries — keyed by component id, so a repathed unit
  keeps its watermark and a surviving `(id, path)` pair keeps its own, not a
  sibling's. Losing one on every sync would silently erase `ab status`'s
  only source of truth about what has landed; advancing a watermark is `ab
  marker stamp`'s job, never sync's.
- **The repo match is the one `ab verify` already makes.** An
  `implemented_by` entry is `repo#path`; its repo half names a repo by path
  suffix (`…/acme/orders` for `acme/orders`, the repo resolved first so a
  relative `--repo` matches on where it actually is), and an entry with no
  `#` names no repo — the single-repo spelling, which speaks for every
  repo. The same rule `absicht.verify._claims` maps changed files by: the
  two readers of `implemented_by` must not disagree about whose code an
  entry names.

`ab marker check` (docs/tasks/45-marker-check.md) is the read-only twin:
the same expected marker, diffed against the file instead of written over
it. It judges the marker's *shape* — which units, which paths — and never
the watermarks (how far behind they are is drift, `ab status`'s entire
subject) nor the marker's `design` field (where a marker points is
discovery, and the store was never asked). Disagreements are findings at
error severity; the README calls a mismatch an error outright.

`ab marker stamp` (docs/tasks/46-marker-stamp.md) is the advancing hand: it
moves exactly one unit's `at`/`design_rev` and never the marker's shape,
which is sync's to write. The README's Discovery section calls the pair
evidence — "a runner bumps both in the commit that lands the work" — so the
watermark stays a claim rather than proof (`done_when` satisfaction is
nobody's guess here, by design). A unit the marker does not carry has no
watermark to move, and a repo with no marker has nothing to move at all:
stamping is not a way to widen the marker, `ab marker sync` is.

Refusal is a feature in all three: a `.absicht/` directory at the repo
root means embedded mode, and sync never converts a store's own repo into
a marker-holding one — nor does check compare against one, since a store's
own repo carries no marker at all. A marker file that does not parse is
refused rather than overwritten — its watermarks cannot be preserved, so
clobbering it would erase them. These raise `MarkerError`, which the CLI
maps to `ExitCode.USAGE`: a broken invocation, not a finding about the
design.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from absicht.codec import CodecError, dump_singleton, parse_singleton
from absicht.findings import RULES, Finding, Severity, finding
from absicht.models import Component, Design, Marker, Ref, UnitWatermark

_MARKER = ".absicht"
"""The discovery file's name, overloaded by filesystem type per the README:
a directory is an embedded store, a file is a reference-mode marker."""


class MarkerError(Exception):
    """Why a marker could not be read or written. A broken invocation, not a
    finding."""


# `marker check`'s rules, registered the way `absicht.check` and `absicht.packet`
# register theirs so `ab check --explain` has one home for every id. All three
# are errors — the README's spec line says a mismatch is an error outright —
# and all three are fixed the same way; the ids differ because what a CI wants
# to exclude or count differs.
RULES.update(
    {
        "marker/missing-unit": (
            "The store's implemented_by names a unit for this repo that the marker "
            "does not carry. The marker is what an agent dropped into the repo reads "
            "to learn what it implements, so one that under-reports silently narrows "
            "that agent's picture. Fix: `ab marker sync --repo PATH`."
        ),
        "marker/moved-unit": (
            "The marker carries a component at a path the store no longer names for "
            "it: the component moved and the marker was not resynced, so it points "
            "at where the code used to be. Fix: `ab marker sync --repo PATH`."
        ),
        "marker/stray-unit": (
            "The marker names a unit the store no longer attributes to this repo. "
            "Composition is the design store's call — the marker is a hint, never "
            "authority — so a stray entry claims work the store says lives "
            "elsewhere. Fix: `ab marker sync --repo PATH`."
        ),
    }
)


def sync(design: Design, repo: Path, *, design_url: str) -> Marker:
    """Write or update `<repo>/.absicht` from the design, returning the marker.

    `design_url` is spelled by the caller (the CLI) — the one thing this
    module deliberately does not decide — and lands in the marker's `design`
    field verbatim.
    """
    if not repo.is_dir():
        raise MarkerError(f"--repo {repo}: no such directory")
    marker_path = repo / _MARKER
    if marker_path.is_dir():
        raise MarkerError(
            f"{marker_path} is a directory: an embedded store, which sync never converts "
            "into a marker-holding repo (the two modes are exclusive)"
        )
    previous = None
    if marker_path.is_file():
        previous = _read(
            marker_path,
            refusal="sync refuses to overwrite it — its watermarks cannot be preserved",
        )
    fresh = _expected(design, repo, design_url=design_url, previous=previous)
    marker_path.write_text(dump_singleton(fresh), encoding="utf-8")
    return fresh


def check(design: Design, repo: Path) -> tuple[Finding, ...]:
    """Every way the marker at `repo` disagrees with `design`.

    Computes the marker `sync` would write — the same expected-marker
    builder, fed the file it just read the way sync would feed it — and
    diffs the two by unit shape. Watermarks and the `design` field are not
    compared (see the module docstring), which is also why the expected
    marker is built with the spelling the file already carries: the field is
    cargo here, not a judgement.
    """
    marker_path = repo / _MARKER
    if marker_path.is_dir():
        raise MarkerError(
            f"{marker_path} is a directory: an embedded store rather than a marker "
            "file, and a store's own repo has no marker to compare"
        )
    if not marker_path.is_file():
        raise MarkerError(f"{marker_path}: no marker to check — `ab marker sync` writes one")
    marker = _read(marker_path, refusal="check cannot compare what it cannot read")
    expected = _expected(design, repo, design_url=marker.design, previous=marker)
    return _disagreements(marker.units, expected.units)


def stamp(repo: Path, unit: Ref, milestone: Ref, *, design_rev: str) -> Marker:
    """Move one unit's watermark to `milestone`/`design_rev`, writing the
    marker back.

    `design_rev` is spelled by the caller (the CLI) — the design store's HEAD
    at invocation time, the README's Discovery section's "design head at the
    time it landed" — so this stays the one blunt move. A unit implemented at
    several paths is one unit: every watermark carrying its id moves, or `ab
    status` would read the stale half as the unit being behind.
    """
    marker_path = repo / _MARKER
    if not marker_path.is_file():
        raise MarkerError(f"{marker_path}: no marker to stamp — `ab marker sync` writes one")
    marker = _read(marker_path, refusal="stamp will not rewrite what it cannot read")
    if all(watermark.id != unit for watermark in marker.units):
        raise MarkerError(
            f"--unit {unit}: the marker carries no such unit — "
            "`ab marker sync` writes the units the store names"
        )
    moved = tuple(
        (
            watermark.model_copy(update={"at": milestone, "design_rev": design_rev})
            if watermark.id == unit
            else watermark
        )
        for watermark in marker.units
    )
    fresh = Marker(design=marker.design, units=moved)
    marker_path.write_text(dump_singleton(fresh), encoding="utf-8")
    return fresh


def _read(marker_path: Path, *, refusal: str) -> Marker:
    """Parse the marker file at `marker_path`, refusing what does not read;
    `refusal` spells why, in the caller's own vocabulary."""
    try:
        return parse_singleton(marker_path.read_text(encoding="utf-8"), model=Marker)
    except (CodecError, OSError) as exc:
        raise MarkerError(
            f"{marker_path}: not a readable .absicht marker ({exc}); {refusal}"
        ) from exc


def _expected(design: Design, repo: Path, *, design_url: str, previous: Marker | None) -> Marker:
    """The marker the design says `repo` should carry: one watermark per
    `implemented_by` entry speaking for `repo`, in the design's own component
    and entry order, with watermarks carried over from `previous` by id."""
    exact = {(unit.id, unit.path): unit for unit in previous.units} if previous else {}
    by_id = {unit.id: unit for unit in previous.units} if previous else {}
    units: dict[tuple[str, str], UnitWatermark] = {}
    for component in design.components:
        for path in _speaks_for(component, repo):
            # Keyed by (id, path), so a repeated entry collapses instead of
            # duplicating a watermark, while two paths of one component stay
            # two watermarks.
            old = exact.get((component.id, path))
            if old is None:
                old = by_id.get(component.id)
            units[(component.id, path)] = (
                old.model_copy(update={"path": path})
                if old is not None
                else UnitWatermark(id=component.id, path=path)
            )
    return Marker(design=design_url, units=tuple(units.values()))


def _speaks_for(component: Component, repo: Path) -> tuple[str, ...]:
    """The `implemented_by` paths of `component` whose entry speaks for `repo`.

    The rule `absicht.verify._claims` applies to a changed file, spelled once
    more here because it is private there and packet-shaped: the repo half of
    an entry names a repo by path suffix, and an entry with no `#` names no
    repo and speaks for every one. The two must stay one rule — a marker that
    disagreed with the scope check about whose code an entry names would make
    `ab status` and `ab verify` answer different questions about the same
    diff.
    """
    resolved = repo.resolve()
    paths: list[str] = []
    for entry in component.implemented_by:
        repo_half, sep, path = entry.partition("#")
        if not sep:
            repo_half, path = "", entry
        name = PurePosixPath(repo_half).parts
        if name and tuple(resolved.parts[-len(name) :]) != name:
            continue
        paths.append(path)
    return tuple(paths)


def _disagreements(
    marked: tuple[UnitWatermark, ...], expected: tuple[UnitWatermark, ...]
) -> tuple[Finding, ...]:
    """The findings between the units a marker carries and the units the store
    says it should carry.

    One finding per disagreeing unit, in the design's order for what the
    store wants and the file's order for what it carries. A path the store
    names that the marker does not is *missing* — unless the marker still
    names the unit somewhere the store no longer does, which is what a move
    looks like and is reported once, as the move, rather than twice as a
    missing unit and a stray one repeating it.
    """
    have = _paths_by_id(marked)
    want = _paths_by_id(expected)
    findings: list[Finding] = []
    for ref, paths in want.items():
        carrying = have.get(ref, ())
        stale = [path for path in carrying if path not in paths]
        for path in paths:
            if path in carrying:
                continue
            if stale:
                findings.append(
                    finding(
                        "marker/moved-unit",
                        severity=Severity.ERROR,
                        message=(
                            f"{ref} is at {', '.join(stale)} in the marker, "
                            f"but the store names {path}"
                        ),
                        ref=ref,
                    )
                )
            else:
                findings.append(
                    finding(
                        "marker/missing-unit",
                        severity=Severity.ERROR,
                        message=f"{ref} at {path} is named by the store but missing from the marker",
                        ref=ref,
                    )
                )
    for ref, paths in have.items():
        named = want.get(ref, ())
        for path in paths:
            # The other half of a move is already reported from the store's
            # side; only a path with no expected counterpart is stray.
            if path in named or set(named) - set(paths):
                continue
            findings.append(
                finding(
                    "marker/stray-unit",
                    severity=Severity.ERROR,
                    message=f"{ref} at {path} is named by the marker but not by the store",
                    ref=ref,
                )
            )
    return tuple(findings)


def _paths_by_id(units: tuple[UnitWatermark, ...]) -> dict[str, list[str]]:
    """Each unit named, with its paths in the order written — the shape
    `check` compares, watermarks dropped on purpose (they are drift, `ab
    status`'s subject, not marker correctness)."""
    paths: dict[str, list[str]] = {}
    for unit in units:
        paths.setdefault(unit.id, []).append(unit.path)
    return paths
