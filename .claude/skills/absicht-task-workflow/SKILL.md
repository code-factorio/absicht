---
name: absicht-task-workflow
description: Operational playbook for absicht task tickets — harness and gate gotchas that CLAUDE.md, the specs and the task prompts do not state.
---

# absicht task-run playbook

Operational facts the binding rules do not state, observed through Render —
READ whole before acting: keyword-grepping it matches nothing.

## Environment and command forms
- The FORCE_COLOR flag-test failure is FIXED (40a1d0b: the test strips
  ANSI; suite green run RAW, even under GITHUB_ACTIONS=true). A
  flag-presence failure now is a NEW color-coupled test, never your diff.
- zsh: words starting with `=` expand (bare `==`, `echo ===`) and unquoted
  non-matching globs abort the command (`--include=*.py`) — quote patterns.
- `ab`'s `--store`/`--rev` are root options: BEFORE the subcommand (after
  it: USAGE error); only `--json` works in both positions.
- `rp` is venv-only (bare `rp` is a 127 — `uv run rp`); `rp comment ID
  "text"` is positional, `rp close` uses `--reason`.
- `docs/users/` doesn't exist yet (docs/: adr, maintainers, spec, tasks).

## Gates and CI
- Local lint green + CI fails I001 = STALE `.ruff_cache` (underscore,
  gitignored) re-serving verdicts — CI runs cacheless; the hyphenated
  `.ruff-cache` isn't ruff's dir. Trust lint only via `ruff check
  --no-cache`; triage CI at `gh run view <id> --log-failed`.
- deptry DEP002 on deps src/ never imports: `rp`, test-only packages and
  mypy `types-*` stubs go in the dev group; commit uv.lock alongside
  pyproject.toml.
- After EVERY edit round `uv run ruff check --fix <files> && uv run ruff
  format <files>`, then re-Read before the next Edit (autofix rewrites
  files). PT011/PT018 on tests, SIM105 on src: no auto-fix.
- `verify.sh mutation` re-serves CACHED verdicts from gitignored `mutants/`
  when only tests changed (`rm -rf mutants` first); check the `[tool.mutmut]`
  paths before running; output: `tr '\r' '\n' | grep -a "mutation:"`.
- Before commit ONE full verify.sh suffices — its test gate IS the whole
  suite; a standalone full pytest just before it doubles the run.
- The live `[[tool.importlinter.contracts]]` block is the only truth
  (specs drift BOTH ways): insert the new layer in place, never reorder.

## Snapshots and fixtures
- Golden `.ambr` are generated, byte-faithful: regenerate via `uv run
  pytest <file>::<test> --snapshot-update`, commit with the change, never
  hand-edit; growing fixtures moves OTHER tickets' snapshots. Count/grep
  fixtures before a red assertion assumes their facts (site: 3 fixes).

## Blocked rounds, reporting, committing
- A blocked round is ONE command, `git status --porcelain`, REVIEWERS too:
  a prior round's verified dirty path plus `git log -1` unmoved IS fresh
  verification, and a zero-commit round needs NO suite run — two reviewers
  burned full verifies re-deriving the chain on a tree equal to HEAD.
  Prior verdicts, even uncommitted: `grep "<ticket>" .rohrpost/log.jsonl`.
- Foreign staged work beside yours: scope commits to your paths; `git add`
  new files first — `git commit -- <path>` on an untracked path errors.
- Commit ids in reports: copy from `git log`, never hand-complete prefixes.
- Backticks in commit messages need `git commit -m "$(cat <<'EOF' ...
  EOF)"` or `-F <file>`; plain -m runs command substitution.
- Multi-line python probes go to /tmp/probe.py; inline `uv run python -c`
  quoting fights the shell.
