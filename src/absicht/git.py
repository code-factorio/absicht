"""One thin place that shells out to git, and only ever reads.

Every feature that needs a revision or a diff — `--rev`, `--diff-base`,
`--changed-only`, `--since`, `ab diff`, `ab marker stamp` — goes through this
module instead of building its own `subprocess.run`, so they all read history
the same way and there is exactly one place for the parts `bandit` exists to
scrutinise: an argv list, never a shell, non-zero exits handled explicitly.

The contract with callers, in the order they trip over it:

- a revision that does not exist raises `GitError` (a broken invocation),
  while a path that does not exist at a known revision is `None` from
  `read_file_at_rev` — callers walking a tree treat the second as expected;
- `resolve_rev` returns a full sha, so anything stamped into a packet or a
  watermark (`design_rev`) is comparable no matter what string was typed;
- `changed_paths` diffs from the merge base (three-dot): what this branch did
  since it left `base`, which is what a CI diff against a base branch means.

No git writes, and no fetch: `origin/HEAD` and friends are read as refs the
local repo already knows; fetching them is the caller's (or CI's) job.
"""

from __future__ import annotations

# The one import bandit's blacklist watches for: this is the one module
# allowed to shell out, and only ever to git, read-only.
import subprocess  # nosec B404
from collections.abc import Sequence
from pathlib import Path


class GitError(Exception):
    """A git invocation failed; the message names the command and git's stderr.

    Raised instead of letting `check=True` surface `CalledProcessError`, so a
    caller sees which git read failed and why without parsing a traceback.
    """

    def __init__(self, command: str, stderr: str) -> None:
        self.command = command
        self.stderr = stderr
        super().__init__(f"{command} failed with: {stderr.strip()}")


def _git(args: Sequence[str], repo: Path) -> subprocess.CompletedProcess[str]:
    """Run git in `repo`, raising `GitError` on any non-zero exit."""
    # Fixed argv, never a shell; "git" resolved from PATH is the point (shims,
    # nix), which is what B603 and B607 would rather be warned about.
    completed = subprocess.run(  # nosec B603 B607
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GitError("git " + " ".join(args), completed.stderr)
    return completed


def current_rev(repo: Path = Path()) -> str:
    """The full sha of what is checked out."""
    return resolve_rev("HEAD", repo)


def resolve_rev(rev: str, repo: Path = Path()) -> str:
    """Turn anything git names a rev with — a branch, `origin/HEAD`, a short
    sha — into the full sha it points at, once, so the rest of a run and
    anything it stamps into a watermark compares full shas."""
    return _git(["rev-parse", rev], repo).stdout.strip()


def read_file_at_rev(path: Path, rev: str, repo: Path = Path()) -> bytes | None:
    """A file's content at `rev`, or `None` when it does not exist there.

    `path` is relative to the repository root, as in `git show <rev>:<path>`,
    which is the shape `list_files_at_rev` returns. The rev is resolved first
    so the two failures stay distinct: a rev that does not exist raises
    `GitError`, while a non-zero exit afterwards can only mean the path is
    absent — "not there yet", an expected outcome for a caller walking a tree.

    Bytes, not text: nothing promises a stored record is valid UTF-8, and the
    codec that decodes it owns that decision.
    """
    sha = resolve_rev(rev, repo)
    # Same bargain as in `_git`: one argument made of the already-resolved sha
    # and a path, never a shell.
    completed = subprocess.run(  # nosec B603 B607
        ["git", "show", f"{sha}:{path.as_posix()}"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout


def list_files_at_rev(dir: Path, rev: str, repo: Path = Path()) -> tuple[Path, ...]:
    """Every file under `dir` at `rev`, recursive, in git's sorted order.

    Paths are relative to the repository root, as `git ls-tree` prints them —
    the same shape `read_file_at_rev` takes, so a caller can enumerate and then
    read. A directory absent at that rev is an empty tuple, not an error: kind
    directories are optional in a store.
    """
    lines = _git(["ls-tree", "-r", "--name-only", rev, "--", dir.as_posix()], repo).stdout
    return tuple(Path(line) for line in lines.splitlines())


def changed_paths(base: str, repo: Path = Path()) -> frozenset[Path]:
    """The paths this branch changed since it diverged from `base`.

    Three-dot, not two: `--changed-only` and `--diff-base` answer "what does
    *this change* touch", and a base branch's own commits after the branch
    point are no part of that — a two-dot diff of the tips would attribute
    them here in reverse. Modified, added and deleted paths all count, and a
    rename can name both sides.

    Paths are relative to the repository root.
    """
    lines = _git(["diff", "--name-only", f"{base}...HEAD"], repo).stdout
    return frozenset(Path(line) for line in lines.splitlines())
