# 05 — `absicht.git`

## Depends on
[00-conventions.md](00-conventions.md).

## Goal

One thin, well-contained place that shells out to `git`, so `--rev`,
`--diff-base`, `--changed-only`, `--since`, `ab diff` and `ab marker stamp`
all read revisions and diffs the same way instead of five call sites each
building their own `subprocess.run`. Small surface, high blast radius if
sloppy (this is exactly what `bandit`'s `security` check exists to catch) —
keep it boring.

## What to build

`src/absicht/git.py`:

- `current_rev(repo: Path = Path()) -> str` — `git rev-parse HEAD`.
- `resolve_rev(rev: str, repo: Path = Path()) -> str` — `git rev-parse
  <rev>`, so callers can turn `origin/HEAD`, a branch, a short sha, into a
  full sha once and pass that around (this is also what makes a `packet.lock`
  or a watermark's `design_rev` meaningful — it should be a full sha, not
  whatever string the user typed).
- `read_file_at_rev(path: Path, rev: str, repo: Path = Path()) -> bytes |
  None` — `git show <rev>:<path>`; `None` (not an exception) when the path
  doesn't exist at that rev, since "not there yet" is an expected outcome for
  callers walking a tree.
- `list_files_at_rev(dir: Path, rev: str, repo: Path = Path()) ->
  tuple[Path, ...]` — enough for [`02-load.md`](02-load.md)'s optional
  git-backed `FileSource` seam to enumerate a store directory at a revision
  (`git ls-tree -r --name-only <rev> -- <dir>`).
- `changed_paths(base: str, repo: Path = Path()) -> frozenset[Path]` — `git
  diff --name-only <base>...HEAD` (three-dot: changes on this branch since it
  diverged from `base`, which is what `--changed-only`/`cli.md`'s default
  `origin/HEAD` implies — confirm three-dot vs two-dot is the intended
  semantics before locking it in; three-dot is almost certainly right for a
  CI diff against a base branch).
- Every function: `subprocess.run([...], cwd=repo, capture_output=True,
  text=True, check=False)` — **argument list, never `shell=True`**, and
  handle a non-zero exit explicitly (raise a `GitError` with the command and
  stderr) rather than letting `check=True` produce Python's generic
  `CalledProcessError`, so callers get a message that names the git command
  that failed.

## Out of scope

- No git *write* operations (no commit, no checkout, no branch management) —
  every caller of this module only ever reads.
- No remote fetch. `origin/HEAD` etc. are read as already-known refs in the
  local repo; fetching them is the caller's (or CI's) job.

## Tests

- Run these against a throwaway git repo built in a `tmp_path` fixture (`git
  init`, a couple of commits, a branch) — not against this repo's own
  history, which will drift and isn't hermetic.
- `read_file_at_rev` for an existing path, a path that doesn't exist at that
  rev, and a rev that doesn't exist (should raise `GitError`, not return
  `None` — those are different failures: "not there" vs "you gave me
  garbage").
- `changed_paths` between two commits matches a hand-built expectation.
- A failing git invocation (e.g. `resolve_rev` on a nonexistent ref) raises
  `GitError` with the stderr text included, not a bare `CalledProcessError`.

## Definition of done

- `absicht.git` added to the import-linter layers list, directly above
  `absicht.models`.
- `bandit` (part of `./scripts/verify.sh fast`) clean on this file
  specifically — it's the one module in the codebase that shells out, so it's
  the one worth a second look.
- `./scripts/verify.sh` clean.
