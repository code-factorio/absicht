"""``absicht.git``: revisions and diffs, read the same way everywhere.

The decisions `docs/tasks/05-git.md` leaves to the implementation are pinned
here:

- "path not there at that rev" is ``None`` and "rev does not exist" is a
  ``GitError`` — a caller walking a tree treats the first as an expected
  outcome and the second as a broken invocation, so the two must not collapse
  into one signal;
- ``changed_paths`` diffs from the merge base (three-dot), so a base branch
  that moved on after this one left it does not smear its own changes into
  "what this change did";
- a failing invocation surfaces as ``GitError`` naming the git command and
  carrying git's stderr, never a bare ``CalledProcessError``.

Every test runs against a throwaway repo built in ``tmp_path``, never against
this repository's own history, which drifts and is not hermetic.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from absicht.git import (
    GitError,
    changed_paths,
    current_rev,
    list_files_at_rev,
    read_file_at_rev,
    resolve_rev,
)


def _run_git(repo: Path, *args: str) -> str:
    """Fixture plumbing: build the throwaway repo, failing loudly if git does."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """One throwaway repo: a first commit on ``main``, a second on a ``feature``
    branch, and a third on ``main`` after the branch point.

    The third commit exists to probe diff semantics: it changed only ``main``,
    so it is exactly what a two-dot diff of the tips would wrongly attribute to
    ``feature``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q", "-b", "main")
    # Commits must work with no global git identity (a bare CI machine) and
    # must not try to sign.
    _run_git(repo, "config", "user.email", "tests@absicht.invalid")
    _run_git(repo, "config", "user.name", "absicht tests")
    _run_git(repo, "config", "commit.gpgsign", "false")

    (repo / ".absicht" / "requirements").mkdir(parents=True)
    (repo / ".absicht" / "system.yaml").write_text("system: v1\n")
    (repo / ".absicht" / "requirements" / "login.md").write_text("login v1\n")
    (repo / "readme.md").write_text("one\n")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-qm", "c1")

    _run_git(repo, "branch", "feature")
    _run_git(repo, "checkout", "-q", "feature")
    (repo / ".absicht" / "requirements" / "login.md").write_text("login v2\n")
    (repo / ".absicht" / "requirements" / "logout.md").write_text("logout\n")
    (repo / "readme.md").unlink()
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-qm", "c2")

    _run_git(repo, "checkout", "-q", "main")
    (repo / "main-only.txt").write_text("main only\n")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-qm", "c3")
    _run_git(repo, "checkout", "-q", "feature")
    return repo


def test_current_rev_is_the_checked_out_commit(repo: Path) -> None:
    assert current_rev(repo) == resolve_rev("feature", repo)


def test_resolve_rev_turns_branches_and_short_shas_into_full_shas(repo: Path) -> None:
    """A watermark's ``design_rev`` must be a full sha: whatever the caller
    typed resolves once, here, and everything downstream compares shas."""
    full = _run_git(repo, "rev-parse", "main").strip()

    assert resolve_rev("main", repo) == full
    assert resolve_rev(full[:7], repo) == full


def test_read_file_at_rev_returns_the_file_as_bytes(repo: Path) -> None:
    assert read_file_at_rev(Path(".absicht/requirements/login.md"), "HEAD", repo) == b"login v2\n"

    first = _run_git(repo, "rev-parse", "main~1").strip()
    assert (
        read_file_at_rev(Path(".absicht/requirements/login.md"), first[:7], repo) == b"login v1\n"
    )


def test_read_file_at_rev_reports_a_path_absent_at_that_rev_as_none(repo: Path) -> None:
    """`readme.md` exists at the first commit but was deleted on `feature`: at
    HEAD it is "not there yet"-style absent, which is an outcome, not an error."""
    assert read_file_at_rev(Path("readme.md"), "HEAD", repo) is None
    assert read_file_at_rev(Path("never/existed.md"), "HEAD", repo) is None


def test_read_file_at_rev_refuses_a_rev_that_does_not_exist(repo: Path) -> None:
    """A garbage rev is a broken invocation, not the same as an absent path."""
    with pytest.raises(GitError):
        read_file_at_rev(Path("readme.md"), "no-such-ref", repo)


def test_list_files_at_rev_enumerates_a_directory_at_that_rev(repo: Path) -> None:
    at_head = list_files_at_rev(Path(".absicht"), "HEAD", repo)

    assert at_head == (
        Path(".absicht/requirements/login.md"),
        Path(".absicht/requirements/logout.md"),
        Path(".absicht/system.yaml"),
    )
    # logout.md is feature-only: the same directory at main is one file smaller.
    assert Path(".absicht/requirements/logout.md") not in list_files_at_rev(
        Path(".absicht"), "main", repo
    )


def test_list_files_at_rev_returns_nothing_for_a_directory_absent_at_that_rev(repo: Path) -> None:
    assert list_files_at_rev(Path("docs"), "HEAD", repo) == ()


def test_changed_paths_matches_the_hand_built_expectation(repo: Path) -> None:
    """What `feature` did since it left `main`: modified, added and deleted.

    `main-only.txt` is the discriminator — it changed on `main` after the
    branch point, so a two-dot diff of the tips includes it and the three-dot
    diff this module promises must not.
    """
    assert changed_paths("main", repo) == frozenset(
        {
            Path(".absicht/requirements/login.md"),
            Path(".absicht/requirements/logout.md"),
            Path("readme.md"),
        }
    )


def test_a_failed_invocation_raises_git_error_with_the_command_and_stderr(repo: Path) -> None:
    with pytest.raises(GitError) as caught:
        resolve_rev("no-such-ref", repo)

    assert caught.value.command == "git rev-parse no-such-ref"
    # git's own diagnostic, carried rather than paraphrased.
    assert "fatal" in caught.value.stderr
    assert caught.value.stderr.strip() in str(caught.value)
