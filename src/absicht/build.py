"""Fold a store into the one artifact everything downstream reads.

``ab build``'s whole job (docs/tasks/20-build.md): load the store, resolve it,
spell it as JSON. Everything after this — the renderer, packets, ``verify`` —
reads the artifact and never the store, so this module is the one place the
"deterministic, byte-identical for the same input" promise has to hold. Every
input to the bytes is pinned somewhere below: `Design`'s field declaration
order is the document's key order (pydantic's default, pinned by test, not
assumed), `load` walks the store in a sorted order, and no layer in the
pipeline reads a clock — `Element` carries no timestamp, so there is nothing
to vary between two runs.

Two refusals, both deliberate:

- a store with `LoadError`s is not built. The spec's determinism promise only
  means something for a store that is actually valid, and an artifact quietly
  folded from "whatever parsed" is a partial build wearing a full build's
  name. `BuildError` lists the files and points at `ab check`; the CLI maps
  it to `ExitCode.FINDINGS` — a true statement about the store, not a broken
  invocation.
- a `--rev` that does not resolve, or a store outside any git repository, is
  `absicht.git`'s `GitError` (or the `ValueError` from the join below),
  passed through for the CLI to map to `ExitCode.USAGE`.
"""

from __future__ import annotations

from pathlib import Path

from absicht.git import list_files_at_rev, read_file_at_rev, repo_root, resolve_rev
from absicht.load import LoadedStore, load_store
from absicht.models.design import Design
from absicht.resolve import resolve


class BuildError(Exception):
    """The store did not load cleanly, so no artifact was built.

    Not a control-flow event for the caller any more than a `LoadError` is
    for `load`: the message names every unreadable file and the command that
    reports them properly, ready to be echoed to stderr as-is.
    """


def _loaded(store: Path, *, rev: str | None) -> LoadedStore:
    """Walk one store with `build`'s refusal: a partial load is not an input.

    Without `rev` the store is read from the working tree. With it, the store
    is read out of git at that revision through the `FileSource` seam
    `absicht.load` left for exactly this (docs/tasks/02-load.md): the same
    walk, a different answer to "does this path exist, what is in it, what
    does it say".
    """
    if rev is None:
        loaded = load_store(store)
    else:
        repo = repo_root(store)
        prefix = store.resolve().relative_to(repo.resolve())
        loaded = load_store(prefix, source=_AtRevision(prefix, rev, repo))
    if loaded.errors:
        details = "\n".join(f"  {error.path}: {error.message}" for error in loaded.errors)
        raise BuildError(
            f"{len(loaded.errors)} file(s) did not load; refusing to build a partial "
            f"artifact. Run `ab check` for the full report:\n{details}"
        )
    return loaded


def build(store: Path, *, rev: str | None = None) -> Design:
    """Load and resolve one store into the `Design` artifact."""
    return resolve(_loaded(store, rev=rev))


def design_json(design: Design) -> str:
    """The artifact's one spelling of the bytes.

    `model_dump_json` walks fields in declaration order, so `models/design.py`
    alone decides the document's shape. Indented, because `--check` diffing a
    stale artifact against a fresh one is read by humans too; the trailing
    newline is the one git's fixers want. The key order is pinned by test — it
    is the load-bearing half of "byte-identical", and nothing in the
    serializer forces it.
    """
    document: str = design.model_dump_json(indent=2)
    return document + "\n"


class _AtRevision:
    """A `load.FileSource` answering from one git revision.

    `load` builds store-relative paths; `absicht.git` names repository-relative
    ones, so the adapter is handed the prefix that joins the two (computed by
    `build`, which knows the store's working-tree location) and passes paths
    straight through. The one translation is `ls-tree`'s recursive listing
    flattened to `list_files`' direct-children contract — without it, a file
    nested under a kind directory would load as an element of that kind.
    """

    def __init__(self, prefix: Path, rev: str, repo: Path) -> None:
        self._repo = repo
        # Resolved once, here: a garbage rev fails before half a store has
        # loaded, and every read below compares full shas.
        self._rev = resolve_rev(rev, repo)
        assert not prefix.is_absolute(), (
            "the prefix is repository-relative, not a working-tree path"
        )

    def exists(self, path: Path) -> bool:
        # A tree answers `git show <rev>:<dir>` as readily as a blob does, so
        # one call covers both kinds of path `load` asks about.
        return read_file_at_rev(path, self._rev, self._repo) is not None

    def list_files(self, directory: Path) -> tuple[Path, ...]:
        return tuple(
            sorted(
                path
                for path in list_files_at_rev(directory, self._rev, self._repo)
                if path.parent == directory
            )
        )

    def read_text(self, path: Path) -> str:
        content = read_file_at_rev(path, self._rev, self._repo)
        if content is None:
            # Only reachable when a file vanishes between listing and reading
            # (a concurrent checkout); `load` already translates OSError into
            # a LoadError, so this keeps its shape rather than inventing one.
            raise FileNotFoundError(f"{path} is absent at the revision")
        return content.decode("utf-8")
