"""The schema-migration seam: a registry, and nothing to run through it yet.

``SCHEMA_VERSION`` is 1 and no other version has ever existed, so there is
nothing to migrate *from*. Per this project's own rules (KISS, YAGNI) this
module is the harness a version-2 change fills in, not an engine built around
an empty registry. What it pins today:

- ``MIGRATIONS``, keyed by the version a migration upgrades *from*, and empty
  because a 1-to-2 entry is the whole of what "version 2 exists" means. The
  registry arms itself the moment that entry lands — no configuration change,
  no remembering — the same stance ``scripts/verify.sh``'s mutation scope
  takes toward ``check.py`` (docs/maintainers/verification.md).
- ``migrate_store``, which answers the questions a caller actually has today:
  is the store current (report and write nothing), is the target reachable
  through registered steps (say where the walk got stuck), and is the ask
  coherent at all (a downgrade or a missing store is a broken invocation).

Where a store would *declare* its version on disk is deliberately undecided:
the current format stamps nothing (records validate against the running
models, ``extra="forbid"``), so every store this binary can resolve is at
``SCHEMA_VERSION``. The change that introduces version 2 owns both a stamp
and its reader — guessing the stamp's location here would calcify a format
decision that belongs to that change.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from absicht.load import StoreResolutionError, resolve_store
from absicht.models import SCHEMA_VERSION

# A migration sees the record's raw field mapping, not a model instance: it
# runs precisely because the record no longer validates against the models of
# the version being migrated to.
type Migration = Callable[[dict[str, object]], dict[str, object]]

MIGRATIONS: dict[int, Migration] = {}
"""The registered upgrade steps, keyed by the version each migrates *from*.

Empty on purpose: schema version 1 is the only version that has ever existed,
so there is nothing to migrate from yet, and an engine built around an empty
registry is the YAGNI violation this project's own rules name. The registry
arms itself the moment a 1-to-2 entry lands — no configuration change, no
remembering.
"""


class MigrationError(Exception):
    """Why a migration was refused. A broken invocation, not a finding."""


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """What one migration run found — the CLI's report is built from this."""

    from_version: int
    """The store's schema version when the run started."""

    to_version: int
    """The version the store is at once the run finished."""


def first_missing_step(current: int, target: int) -> int | None:
    """The first version on the walk from ``current`` to ``target`` with no
    registered migration; ``None`` when the whole path is registered."""
    for version in range(current, target):
        if version not in MIGRATIONS:
            return version
    return None


def migrate_store(root: Path, *, to: int | None = None) -> MigrationResult:
    """Migrate the store at ``root`` to ``to``, default the latest known version.

    A store at the target is already current and nothing is written. A target
    the registered steps cannot reach raises ``MigrationError`` naming the
    version the walk got stuck on — and so does a downgrade or a missing
    store: all three are broken invocations, not findings about the design.
    """
    try:
        resolve_store(root)
    except StoreResolutionError as exc:
        raise MigrationError(str(exc)) from exc
    # No on-disk stamp exists to read: version 1 is the only version there
    # has ever been, so a store this binary can resolve is at the running
    # version. The version-2 change owns the stamp and its reader.
    current = SCHEMA_VERSION
    target = SCHEMA_VERSION if to is None else to
    if target < current:
        raise MigrationError(
            f"cannot migrate from {current} to {target}: a store never moves to an older schema"
        )
    if target == current:
        return MigrationResult(from_version=current, to_version=target)
    if (stuck := first_missing_step(current, target)) is not None:
        raise MigrationError(f"don't know how to migrate from {stuck}")
    # Only reachable once MIGRATIONS holds a complete chain, which arrives
    # together with the applier that runs it. Before that, a complete chain
    # means one was registered without an applier — a bug in ab itself, and
    # refusing loudly beats a success report that moved nothing.
    raise NotImplementedError(f"applying a registered migration to {target}")
