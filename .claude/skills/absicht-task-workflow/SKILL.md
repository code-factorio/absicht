---
name: absicht-task-workflow
description: Operational playbook for absicht task tickets — harness and gate gotchas that CLAUDE.md, the specs and the task prompts do not state.
---

# absicht task-run playbook

Operational facts the binding rules do not state, observed through Render.
READ this file whole before your first suite call — keyword-grepping it for
the topic of the moment ('dirty', 'untracked') matches nothing: two Render
reviewers did, then ran a raw suite and re-derived FORCE_COLOR from scratch.

## Environment and command forms

- Prefix EVERY suite invocation — verify.sh and pytest, FIRST call of the
  session included — with `env -u FORCE_COLOR -u COLORTERM`: the shell
  exports FORCE_COLOR=3 and rich ANSI-splits `--flag`, failing the
  flag-presence cases in tests/test_cli.py. Pre-exists every diff, never
  yours; 18 reviewers have re-derived this, impl agents that read here don't.
- zsh expands a word starting with `=`: `echo ===` and bare `==` fail.
- `ab`'s `--store`/`--rev` are root options: pass them BEFORE the subcommand
  (after it they are USAGE errors); only `--json` works in both positions.
- `rp` lives in the project venv only — bare `rp show` is a 127; invoke
  `uv run rp`. `rp comment ID "text"` takes the note POSITIONALLY (no
  `--text`; `rp close` uses `--reason`); check `rp <cmd> -h` first.
- `docs/users/` doesn't exist yet (docs/: adr, maintainers, spec, tasks) —
  create it on first use, don't `ls` it.

## Gates

- deptry DEP002 fires on `[project.dependencies]` entries src/ never imports:
  uv-run-only tools (rohrpost `rp`), test-only packages and mypy's `types-*`
  stubs go in the dev group; `uv lock` and commit uv.lock with pyproject.toml.
- After EVERY edit round: `uv run ruff check --fix <files> && uv run ruff
  format <files>`. Besides I001/format, PT011/PT018 fire on new test files
  with NO auto-fix — budget a hand-fix round. Autofix rewrites files:
  re-Read before the next Edit or the old_string misses.
- `verify.sh mutation` takes minutes and mutmut re-serves CACHED verdicts
  from gitignored `mutants/` when only tests changed — `rm -rf mutants`
  first; its \r-spinner-padded output reads via `tr '\r' '\n' |
  grep -a "mutation:"`, survivors via `uv run mutmut results`.
- The live `[[tool.importlinter.contracts]]` block is the only truth (specs
  drift from it in BOTH directions): insert the new layer in place, never
  reorder — pasting from a doc makes Edit miss.

## Snapshots and fixtures

- Golden `.ambr` files are generated, byte-faithful output: regenerate with
  `env -u FORCE_COLOR -u COLORTERM uv run pytest <file>::<test>
  --snapshot-update` and commit the `.ambr` with the change. Growing a
  fixture system moves OTHER tickets' snapshots (gaps moved test_build.ambr).
  Never hand-edit them — tests/__snapshots__/ is excluded from the
  trailing-whitespace hook for that reason. Grep fixtures before a red
  assertion assumes an edge or owner they may not have.

## Blocked rounds, reporting, committing

- The pre-work dirty-tree mandate is ONE command, `git status --porcelain`:
  the same sole dirty path the prior round already verified plus `git
  log -1` unmoved IS fresh verification — stop and return blocked. Five
  Render rounds re-derived the full forensic chain (check-ignore, log
  --all, repo grep, mtime, stash) their own prompt had already quoted, and
  re-read the 405-line blocker whole — `head -5` of its status header
  classifies it.
- Prior verdicts are one-grep evidence even when uncommitted: `grep
  "<ticket>" .rohrpost/log.jsonl` and `git diff -- .rohrpost/log.jsonl` —
  the c8vrry failure verdict corroborated the identical 1q9ymw blocker.
- Commit ids in a return value or ticket comment: copy from `git log`
  output — completing short prefixes by hand ships wrong full SHAs.
- Commit messages containing backticks need `git commit -m "$(cat <<'EOF'
  ... EOF)"` or `-F <file>`; plain `-m` runs them as command substitution.
- Multi-line python probes: write /tmp/probe.py and run it; inline
  `uv run python -c` with nested quotes fights the shell.
