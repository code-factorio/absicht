---
name: absicht-task-workflow
description: Operational playbook for absicht task tickets — harness and gate gotchas that CLAUDE.md, the specs and the task prompts do not state.
---

# absicht task-run playbook

Operational facts the binding rules do not state, observed through the addendum rounds — READ whole: grepping it for keywords matches nothing.

## Environment and command forms
- zsh still bites: a word starting with `=` (`echo ===`, `=====`) fails expansion AND THE REST OF THE LINE NEVER RUNS — earlier output returns, later commands are silently skipped, so it reads like truncated success. Unquoted non-matching globs abort the line too.
- EVERY Bash call failing with no output — even `echo alive` — is an exhausted user disk quota: the Bash tool captures output through /tmp and dies before reporting, while commands still run. Exit codes turn garbage tool-wide (echo→1, `uv run`→120, git→128); /tmp files come back empty; Write to /tmp reports EDQUOT while Write to $HOME succeeds. Do not probe the shell or diagnose per command — agents burned 40, then 90, then 40 more calls on it.
- The brick is often SELF-inflicted and clears with the debris gone: keep the red-proof worktree and every scratch store under /var/tmp, never /tmp — a /tmp worktree plus its pytest run is exactly what tipped it mid-review. Escape: append `> /var/tmp/x.txt 2>&1; true` and Read the file back; locate debris with `du -sh /tmp/* | sort -rh` (stale caches held 6.8G once) and `rm -rf mutants`.
- Shell still dead but the ticket must be closed: Write a python driver to $HOME that `shutil.rmtree`s the /tmp debris, then subprocess-runs the rp/git steps one by one, appending each result to a $HOME log; run it with `uv run python <driver>` and `git push` once output returns. This carried a bricked review to a green push.
- `ab`'s `--store`/`--rev` are root options: BEFORE the subcommand; only `--json` works in both. `rp` is venv-only (`uv run rp`); `rp comment ID "text"` is positional, `rp close` uses `--reason`.
- `ab init` writes only into a dir that does NOT yet exist: `--store <existing empty dir> init` is refused ("already exists: pass --force"). Smoke tests should mkdir only the cwd and point `--store` at a still-missing subdir.
- A "[model] temporarily unavailable … cannot determine the safety of Bash" tool error is transient: continue read-only, retry unchanged.

## Fixtures and smoke tests
- tests/fixtures/systems/<name>/ IS a store root: element dirs sit at the top (stories/, milestones/, …, system.yaml) with NO `.absicht/` inside — grep `<name>/<kind>/*.md`, never `<name>/.absicht/<kind>/`.
- Smoke-testing outside the repo: a fixture copy carries no marker, so default store discovery refuses it (`no store at .absicht`) — drive it with `uv run --project <repo> ab --store <copy> …` from one sandbox cwd; `--out` and build paths resolve against the cwd, not the store.
- Golden `.ambr` are generated, byte-faithful: `uv run pytest <file>::<test> --snapshot-update`, commit with the change; growing fixtures moves OTHER tickets' snapshots. Grep fixture facts before a red assertion.
- Exact-output tests authored before the implementation get their bytes wrong (hand-counted padding, a missing fixture owner, the init-scaffolded system element): when the fresh suite fails, probe the REAL output with a scratch store before debugging the implementation — the defect is often the expectation. Test corrections land as their own tests-only commit BEFORE the implementation commit, so red-at-tests stays provable.

## Gates and CI
- Piped or redirected verify/gh output still carries ANSI codes — strip with `sed 's/\x1b\[[0-9;]*m//g'` before grep. A flag-presence test failing locally is a NEW color-coupled test, not the environment.
- Local lint green + CI fails I001 = stale `.ruff_cache` (underscore, gitignored) re-serving verdicts — trust lint only via `ruff check --no-cache`.
- CI red on a test your ticket never touched: suspect clock/ordering-dependent fixtures. The classic was two scratch `git commit`s assumed to share a sha — true only within one wall-clock second ("Invalid symmetric difference expression", CI only). Pin GIT_AUTHOR_DATE/GIT_COMMITTER_DATE in the fixture and land the pin inside your own push: main must go green again.
- deptry DEP002 on deps src/ never imports: `rp`, test-only packages and mypy `types-*` stubs go in the dev group; commit uv.lock with pyproject.
- After EVERY edit round `ruff check --fix && ruff format` the touched files, then re-Read before the next Edit. Not auto-fixed: PT011/PT018 on tests; SIM105 and PERF401 on src.
- The live `[[tool.importlinter.contracts]]` block is the only truth (specs drift BOTH ways): insert the new layer in place, never reorder.
- Before a commit ONE full verify.sh suffices — its test gate IS the whole suite; a standalone full pytest right before it doubles the run.

## Mutation economy
- Owed only when tests of MUTATION_SCOPE (model/, check.py, packet.py) changed — check that first; render/, cli/ and verify.py are NOT gated and the gate is a floor (45%), not zero survivors: perfecting ungated code cost two extra minutes-long runs on one ticket.
- A full run is ~3600 mutants, minutes long: launch it as a background task and poll its output file `/tmp/claude-1000/<project>/<session>/tasks/<id>.output` after a sleep instead of blocking. `rm -rf mutants` before a run whose score you will trust — and see the quota lines before starting one.
- Filter verdicts `tr '\r' '\n' | grep -a "mutation:"`, survivors via `uv run mutmut results`; iterate on survivors by name (`uv run mutmut run absicht.render.x__…`) instead of full re-runs.

## Starting, reporting, committing
- FIRST move on any dispatched ticket: `grep <id> .rohrpost/log.jsonl` and `git log --oneline --grep=<slug>` — one arrived already delivered by an earlier round (implement became claim + audit). The same inspection covers a predecessor that DIED mid-round (claim + tests-first commit at HEAD, uncommitted half-implementation in the tree): audit that working-tree diff against the spec line by line, finish it, land it as your own implementation commit.
- Proving tests-first red cheaply when you must see it yourself: `git worktree add --detach /var/tmp/x <tests-commit>` then `uv run pytest <file>` — the ImportError of the not-yet-existing name IS the red proof. Keep the worktree under /var/tmp (quota); a reviewer can often trust the handoff's stated red evidence (failure count + missing name) instead.
- Full SHAs in rp comments: paste from output or interpolate `$(git rev-parse …)` — hand-completing a prefix shipped a wrong tail twice; the log is append-only, so each fix costs another commit.
- Foreign staged work beside yours: scope commits to your paths; `git add` new files first — `git commit -- <path>` on an untracked path errors.
- Backticks in commit messages need `git commit -m "$(cat <<'EOF' … EOF)"` or `-F <file>`. Multi-line python probes go to a /var/tmp file, never inline `uv run python -c`.
