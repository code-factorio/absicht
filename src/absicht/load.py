"""Walk a store on disk into raw per-kind tuples, tolerant of bad files.

`load` is the only layer that knows a store is a directory layout (pinned in
`docs/tasks/00-conventions.md`): `system.yaml` plus one directory per kind,
one `<slug>.md` file per element. Everything above it — `check`, `build`,
`packet` — reads a `LoadedStore` and never a `Path`.

Tolerance is the contract: one broken file is one `LoadError` and the walk
continues, so a store with a single typo still yields everything else and
`ab check` can report the file instead of crashing. `LoadError` deliberately
knows nothing of `absicht.findings` severities — `check` translates; `build`
and `packet` just want the data plus a list of what went wrong.

`layout.yaml` is not read yet: there is no positions model to read it into
(`docs/tasks/25-layout.md`), and guessing a shape ahead of one is how formats
calcify. `resolve_store` lands the store-location modes from `cli.md`'s global
flags table — the CLI maps its failure to `ExitCode.USAGE`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from absicht.codec import (
    CodecError,
    CodecValidationError,
    parse_element,
    parse_singleton,
)
from absicht.models import (
    Component,
    DataEntity,
    Decision,
    Element,
    External,
    Marker,
    Milestone,
    NonFunctional,
    Question,
    Rejection,
    Requirement,
    Seam,
    Story,
    System,
)

_SYSTEM = "system.yaml"

_SYSTEM_MISSING = f"{_SYSTEM} is missing: a store needs exactly one System element"


class LoadErrorReason(StrEnum):
    """Which family a load failure belongs to.

    The discriminator `absicht.check` maps to a rule id; without it, mapping
    a `LoadError` to a finding would mean parsing its message.
    """

    SYNTAX = "syntax"
    """The codec could not read the file as the format at all."""
    VALIDATION = "validation"
    """The file parsed, but its fields did not validate."""
    MISSING_SYSTEM = "missing-system"
    """No `system.yaml`: a store needs exactly one System element."""
    IO = "io"
    """The file could not be read, never mind parsed."""


@dataclass(frozen=True, slots=True)
class LoadError:
    """One file that could not be read, and why.

    Not an exception: a store with bad files is a normal outcome that `check`
    reports as findings and `build` skips over, not a control-flow event.
    """

    path: str
    """Store-relative, POSIX-style — the same spelling `Element.source` uses."""

    message: str
    """What is wrong, in the vocabulary of the caller (a `CodecError` message)."""

    reason: LoadErrorReason
    """The failure family, so `check` picks a rule id by lookup, not by parsing `message`."""


@dataclass(frozen=True, slots=True)
class LoadedStore:
    """A store as raw per-kind tuples: parsed, sorted, unresolved.

    Mirrors `Design`'s fields minus `system`, which is optional here because a
    store without a `system.yaml` still has elements worth reporting on.
    Refusing to fold a systemless store is `build`'s job, one layer up.
    """

    system: System | None
    externals: tuple[External, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    non_functionals: tuple[NonFunctional, ...] = ()
    stories: tuple[Story, ...] = ()
    components: tuple[Component, ...] = ()
    seams: tuple[Seam, ...] = ()
    data: tuple[DataEntity, ...] = ()
    decisions: tuple[Decision, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    questions: tuple[Question, ...] = ()
    milestones: tuple[Milestone, ...] = ()
    errors: tuple[LoadError, ...] = ()


class FileSource(Protocol):
    """Where `load_store` reads files from: the working tree now, a git
    revision once `absicht.git` supplies an implementation.

    Paths are the store-root-relative paths `load_store` builds; an
    implementation translates them to wherever its files live. This is the one
    seam that task needs — do not grow it.
    """

    def exists(self, path: Path) -> bool: ...

    def list_files(self, directory: Path) -> tuple[Path, ...]:
        """The files directly inside a directory, sorted by name; no recursion."""
        ...

    def read_text(self, path: Path) -> str: ...


class WorkingTree:
    """The default `FileSource`: the store as it sits on the working tree."""

    def exists(self, path: Path) -> bool:
        return path.exists()

    def list_files(self, directory: Path) -> tuple[Path, ...]:
        return tuple(sorted(entry for entry in directory.iterdir() if entry.is_file()))

    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")


def load_store(root: Path, *, source: FileSource | None = None) -> LoadedStore:
    """Walk one store root into a `LoadedStore`, in a stable order.

    `system.yaml` first, then one kind directory at a time in `Design`'s field
    order, files within a kind sorted by name — determinism downstream
    (`build` is byte-stable) starts here. A missing kind directory is an empty
    tuple and a bad file a `LoadError`; neither stops the walk.
    """
    src = source if source is not None else WorkingTree()
    errors: list[LoadError] = []
    return LoadedStore(
        system=_load_system(root, src, errors),
        externals=_load_kind(root, src, "externals", External, errors),
        requirements=_load_kind(root, src, "requirements", Requirement, errors),
        non_functionals=_load_kind(root, src, "non_functionals", NonFunctional, errors),
        stories=_load_kind(root, src, "stories", Story, errors),
        components=_load_kind(root, src, "components", Component, errors),
        seams=_load_kind(root, src, "seams", Seam, errors),
        data=_load_kind(root, src, "data", DataEntity, errors),
        decisions=_load_kind(root, src, "decisions", Decision, errors),
        rejections=_load_kind(root, src, "rejections", Rejection, errors),
        questions=_load_kind(root, src, "questions", Question, errors),
        milestones=_load_kind(root, src, "milestones", Milestone, errors),
        errors=tuple(errors),
    )


def _load_system(root: Path, source: FileSource, errors: list[LoadError]) -> System | None:
    path = root / _SYSTEM
    if not source.exists(path):
        errors.append(
            LoadError(path=_SYSTEM, message=_SYSTEM_MISSING, reason=LoadErrorReason.MISSING_SYSTEM)
        )
        return None
    try:
        return parse_singleton(source.read_text(path), model=System)
    except (CodecError, OSError) as exc:
        errors.append(LoadError(path=_SYSTEM, message=str(exc), reason=_reason(exc)))
        return None


def _load_kind[E: Element](
    root: Path, source: FileSource, directory: str, model: type[E], errors: list[LoadError]
) -> tuple[E, ...]:
    kind_dir = root / directory
    if not source.exists(kind_dir):
        return ()
    loaded: list[E] = []
    for path in source.list_files(kind_dir):
        if path.suffix != ".md":
            continue  # only `<slug>.md` files are elements; a .gitkeep is neither
        source_path = path.relative_to(root).as_posix()
        try:
            loaded.append(parse_element(source.read_text(path), model=model, source=source_path))
        except (CodecError, OSError) as exc:
            errors.append(LoadError(path=source_path, message=str(exc), reason=_reason(exc)))
    return tuple(loaded)


def _reason(exc: Exception) -> LoadErrorReason:
    """Classify what one file failed on, for the rule lookup one layer up."""
    if isinstance(exc, CodecValidationError):
        return LoadErrorReason.VALIDATION
    if isinstance(exc, CodecError):  # the base and the syntax subclass alike: not the format
        return LoadErrorReason.SYNTAX
    return LoadErrorReason.IO


class StoreResolutionError(Exception):
    """The store location does not name a usable store.

    The CLI reports this as ``ExitCode.USAGE``: a broken invocation ("no
    store" in the exit-code table), not a finding about the design.
    """


_REMOTE_DESIGN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://|^[\w.-]+@[\w.-]+:")
"""`design:` targets that would need fetching: URLs and scp-style git remotes.

A remote design is used today by checking it out and naming the local path,
so anything that needs the network is refused with a clear message instead of
a silent partial fetch.
"""


def resolve_store(path: Path) -> Path:
    """Resolve a store location — `--store`, `$ABSICHT_STORE` or `.absicht`.

    Embedded mode: the path is a directory and is the store itself. Reference
    mode: the path is a `.absicht` marker file whose `design` names the store,
    resolved against the marker's directory when relative, so a marker and the
    store it names travel together. Remote `design:` targets are not supported
    yet — check the store out and name the checkout.

    Raises `StoreResolutionError` when there is no store to load.
    """
    if path.is_dir():
        return path
    if not path.is_file():
        raise StoreResolutionError(
            f"no store at {path}: not a store directory and not a .absicht marker file"
        )
    marker = _read_marker(path)
    if _REMOTE_DESIGN.match(marker.design):
        raise StoreResolutionError(
            f"the marker at {path} names the remote design {marker.design!r}, "
            "which is not supported yet; check the store out and name the local path"
        )
    design = Path(marker.design)
    if not design.is_absolute():
        design = path.parent / design
    # normpath, not resolve(): collapse a relative `..` lexically without
    # following symlinks, so the returned path stays the path that was named.
    design = Path(os.path.normpath(design))
    if not design.is_dir():
        raise StoreResolutionError(
            f"the marker at {path} names {design}, which is not a store directory"
        )
    return design


def _read_marker(path: Path) -> Marker:
    try:
        return parse_singleton(path.read_text(encoding="utf-8"), model=Marker)
    except (CodecError, OSError) as exc:
        raise StoreResolutionError(f"{path} is not a readable .absicht marker: {exc}") from exc
