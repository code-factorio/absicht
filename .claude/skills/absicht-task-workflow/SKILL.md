---
name: absicht-task-workflow
description: Operational playbook for absicht task tickets — harness and gate gotchas that CLAUDE.md, the specs and the task prompts do not state.
---

# absicht task-run playbook

Operational facts the binding rules do not state, observed through Packet & verify — READ whole: grepping it for keywords matches nothing.

## Environment and command forms
- zsh still bites: a word starting with `=` (`echo ===`, `=====`) fails expansion AND THE REST OF THE LINE NEVER RUNS — earlier output returns, later commands are silently skipped, so it reads like truncated success (two reviewers this phase). Unquoted non-matching globs abort the line too.
- `ab`'s `--store`/`--rev` are root options: BEFORE the subcommand; only `--json` works in both. `rp` is venv-only (`uv run rp`); `rp comment ID "text"` is positional, `rp close` uses `--reason`.
- A "[model] temporarily unavailable … cannot determine the safety of Bash" tool error is transient: continue read-only, retry unchanged.

## Fixtures and smoke tests
- tests/fixtures/systems/<name>/ IS a store root: element dirs sit at the top (stories/, milestones/, …, system.yaml) with NO `.absicht/` inside — grep `<name>/<kind>/*.md`, never `<name>/.absicht/<kind>/`.
- Smoke-testing in /tmp: a fixture copy carries no marker, so default store discovery refuses it (`no store at .absicht`) — drive it with `uv run --project <repo> ab --store <copy> …` from one sandbox cwd; `--out` and build paths resolve against the cwd, not the store.
- Golden `.ambr` are generated, byte-faithful: `uv run pytest <file>::<test> --snapshot-update`, commit with the change; growing fixtures moves OTHER tickets' snapshots. Grep fixture facts before a red assertion.

## Gates and CI
- Run verify/pytest bare: the FORCE_COLOR flag-test failure is fixed (40a1d0b); a flag-presence failure now is a NEW color-coupled test.
- Local lint green + CI fails I001 = stale `.ruff_cache` (underscore, gitignored) re-serving verdicts — trust lint only via `ruff check --no-cache`; triage CI at `gh run view <id> --log-failed`.
- deptry DEP002 on deps src/ never imports: `rp`, test-only packages and mypy `types-*` stubs go in the dev group; commit uv.lock with pyproject.
- After EVERY edit round `ruff check --fix && ruff format` the touched files, then re-Read before the next Edit. Not auto-fixed: PT011/PT018 on tests; SIM105 and PERF401 on src.
- The live `[[tool.importlinter.contracts]]` block is the only truth (specs drift BOTH ways): insert the new layer in place, never reorder.
- Before a commit ONE full verify.sh suffices — its test gate IS the whole suite; a standalone full pytest right before it doubles the run.

## Mutation economy
- Owed only when tests of MUTATION_SCOPE (model/, check.py, packet.py) changed — check that first; render/, cli/ and verify.py are NOT gated and the gate is a floor (45%), not zero survivors: perfecting ungated code cost two extra minutes-long runs on one ticket.
- Iterate on survivors by name (`uv run mutmut run absicht.render.x__…`) instead of full re-runs; `rm -rf mutants` before a run whose score you will trust; verdicts via `tr '\r' '\n' | grep -a "mutation:"`, survivors via `uv run mutmut results`.

## Starting, reporting, committing
- FIRST move on any dispatched ticket: `grep <id> .rohrpost/log.jsonl` and `git log --oneline --grep=<slug>` — one arrived already delivered by an earlier round (implement became claim + audit). The same grep settles blocked rounds: a prior verdict plus unmoved HEAD is fresh verification, and a zero-commit round needs no suite run (reviewers included).
- Full SHAs in rp comments: paste from output or interpolate `$(git rev-parse …)` — hand-completing a prefix shipped a wrong tail twice; the log is append-only, so each fix costs another commit.
- Foreign staged work beside yours: scope commits to your paths; `git add` new files first — `git commit -- <path>` on an untracked path errors.
- Backticks in commit messages need `git commit -m "$(cat <<'EOF' … EOF)"` or `-F <file>`. Multi-line python probes go to a /tmp file, never inline `uv run python -c`.
