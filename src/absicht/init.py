"""Scaffold a store: the one command that writes before anything else exists.

`ab init` chooses a mode explicitly (`docs/spec/cli.md#ab-init`) and this
module is the whole decision: embedded mode writes a `system.yaml` — the one
file a store cannot derive — and reference mode writes a `.absicht` marker
pointing elsewhere. The kind directories of `docs/tasks/00-conventions.md`'s
layout are deliberately not created: `absicht.load` reads a missing directory
as "no elements", and git could not hold an empty one anyway.

Refusal is the feature. `init` never overwrites, and `--force` relaxes the
already-exists check only for a store nothing has been authored into yet —
a scaffolded `system.yaml` does not count as an element, any
`<kind>/<slug>.md` does. The CLI maps `InitError` to `ExitCode.USAGE`: a
broken invocation, not a finding about a design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from absicht.codec import dump_singleton
from absicht.models import Marker, System

_SYSTEM_FILE = "system.yaml"


class InitError(Exception):
    """Why a scaffold was refused. A broken invocation, not a finding."""


@dataclass(frozen=True, slots=True)
class InitResult:
    """What one scaffold run wrote — the CLI's report is built from this."""

    mode: Literal["embedded", "reference"]
    """The store-location mode that was chosen, never inferred."""

    path: Path
    """The file this run created."""


def init_embedded(root: Path, name: str | None, *, force: bool = False) -> InitResult:
    """Scaffold `root` as an embedded store: one `system.yaml`, nothing else."""
    if not name or not name.strip():
        raise InitError("a system needs a name: pass --name NAME")
    slug = _slugify(name)
    if not slug:
        raise InitError(f"the name {name!r} has no letters or digits to build an id from")
    if root.is_file():
        # A marker in reference mode occupies the name; switching modes is
        # `ab extract` or a deletion the user makes, never a silent overwrite.
        raise InitError(
            f"a marker file already sits at {root}: init never overwrites; "
            "switch modes with ab extract or delete it yourself"
        )
    if root.is_dir():
        if _has_elements(root):
            raise InitError(
                f"the store at {root} already has elements: --force writes into an empty store only"
            )
        if not force:
            raise InitError(f"the store at {root} already exists: pass --force to write into it")
    system_file = root / _SYSTEM_FILE
    root.mkdir(parents=True, exist_ok=True)
    system_file.write_text(
        dump_singleton(System(id=f"system:{slug}", title=name)), encoding="utf-8"
    )
    return InitResult(mode="embedded", path=system_file)


def init_reference(marker: Path, design: str) -> InitResult:
    """Write `marker` as a reference-mode `.absicht` file; no store directory.

    There is no `force` parameter on purpose: `--force` relaxes the
    already-exists check for an *empty store*, and a marker is never that —
    overwriting one would silently re-point a repo at another design.
    """
    if not design.strip():
        raise InitError("a reference store needs a URL: pass --reference URL")
    if marker.exists():
        raise InitError(f"{marker} already exists: init never overwrites")
    marker.write_text(dump_singleton(Marker(design=design)), encoding="utf-8")
    return InitResult(mode="reference", path=marker)


def _slugify(name: str) -> str:
    """Fold a display name into the `Slug` vocabulary: `ACME Orders!` -> `acme-orders`."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _has_elements(root: Path) -> bool:
    """Elements are `<kind>/<slug>.md` files — the scaffold itself is not one.

    This is the `--force` line: the check may pass over a store holding only
    `system.yaml` (or layout.yaml, or a .gitkeep), never over one an element
    has been authored into, whatever that element validates to.
    """
    return any(root.glob("*/*.md"))
