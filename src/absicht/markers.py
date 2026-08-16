"""Write a repo's `.absicht` marker from the design store.

`ab marker sync` (docs/tasks/44-marker-sync.md) is the store's half of the
discovery bargain the README's Discovery section describes: the implementing
repo gets a regenerable hint naming where the design lives and which units
this repo implements, while the store stays authoritative. Two rules carry
the whole module:

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

Refusal is a feature here too: a `.absicht/` directory at the repo root
means embedded mode, and sync never converts a store's own repo into a
marker-holding one. A marker file that does not parse is refused rather
than overwritten — its watermarks cannot be preserved, so clobbering it
would erase them. Both raise `MarkerError`, which the CLI maps to
`ExitCode.USAGE`: a broken invocation, not a finding about the design.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from absicht.codec import CodecError, dump_singleton, parse_singleton
from absicht.models import Component, Design, Marker, UnitWatermark

_MARKER = ".absicht"
"""The discovery file's name, overloaded by filesystem type per the README:
a directory is an embedded store, a file is a reference-mode marker."""


class MarkerError(Exception):
    """Why a marker could not be written. A broken invocation, not a finding."""


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
        previous = _read(marker_path)
    fresh = _expected(design, repo, design_url=design_url, previous=previous)
    marker_path.write_text(dump_singleton(fresh), encoding="utf-8")
    return fresh


def _read(marker_path: Path) -> Marker:
    """Parse the marker file at `marker_path`, refusing what does not read."""
    try:
        return parse_singleton(marker_path.read_text(encoding="utf-8"), model=Marker)
    except (CodecError, OSError) as exc:
        raise MarkerError(
            f"{marker_path}: not a readable .absicht marker ({exc}); "
            "sync refuses to overwrite it — its watermarks cannot be preserved"
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
