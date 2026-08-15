# 00 — Conventions every task shares

Not a command, not a module. Read this before starting any other file in
`docs/tasks/` — it pins the decisions that would otherwise get made
differently by every task, and the tasks below assume it rather than
repeating it.

## The layer stack

`pyproject.toml`'s `[[tool.importlinter.contracts]]` names the stack this
project is growing into, bottom to top. A module may import anything below it
in this list, nothing above:

```
absicht.__main__
absicht.cli
absicht.status | absicht.markers
absicht.render | absicht.packet | absicht.verify   # resolved graph, read-only
absicht.build
absicht.check
absicht.resolve
absicht.load
absicht.codec
absicht.git
absicht.findings                                    # cross-cutting, import from check/verify
absicht.models                                       # imports nothing of ours
```

Only listed layers are enforced — `import-linter` fails on a named module
that doesn't exist yet, so **add each new module to the list in the same
commit that creates it**, not as a follow-up. This is the rule that keeps the
file format swappable (nothing below `codec` knows how a record is spelled on
disk) and the core reusable behind a future web/MCP surface (nothing below
`cli` knows it's being run from a terminal) — see
[`../maintainers/verification.md`](../maintainers/verification.md#the-import-contracts).

`absicht.findings` is cross-cutting (severities, the `Finding`/`Report`
shape, text/json/sarif rendering) and is imported by both `check` and
`verify`; it sits low enough that both can reach it. `absicht.git` is a thin
subprocess wrapper for reading the store at a revision and computing diffs;
several layers reach into it (`load` for `--rev`, `build`/`check` for
`--changed-only`, `packet` for `--seal`, `verify`/`status`/`diff` for
`--diff-base`/`--since`), so it sits near the bottom, above only `models`.

`absicht.cli` already exists (`src/absicht/cli/`) and stays a thin adapter:
no business logic, no `print` outside rendering, no `sys.exit` — commands
resolve arguments, call the library, render the result. See
`src/absicht/cli/__init__.py`'s module docstring; it is not decoration.

## Reality check before trusting this document

Everything above and below reflects the codebase as read while these tasks
were written. Before acting on a claim here that names a specific file,
function or module — confirm it still exists; code moves faster than task
lists. `CONTEXT.md` says schema structs live under `model/` using `msgspec` —
that's stale. The real, current implementation is `src/absicht/models.py`
using `pydantic`. Trust the code over the doc when they disagree, and prefer
what `git log` / a fresh `Read` shows over anything cached here.

## On-disk file format (not yet decided anywhere else — this pins it)

The README's tree diagram is illustrative, not exhaustive — it shows
`decisions/` and `milestones/` but not `rejections/`, `questions/`, `nfr` or
`externals`, and none of `absicht.cli._common.Kind`'s eleven values map to a
directory today. The simplest rule that stays predictable: **one directory
per `Kind`, matching `Design`'s own field names**:

```
.absicht/
├── system.yaml           # singleton, no directory — the one System element
├── requirements/
├── non_functionals/
├── stories/
├── components/
├── seams/
├── data/
├── decisions/
├── rejections/
├── questions/
├── milestones/
├── externals/
└── layout.yaml           # singleton, produced/maintained by `ab layout`
```

One element per file. Filename is `<slug>.md` (the `SLUG` half of the
`kind:slug` id — see `Ref` and `Slug` in `models.py`). File content is YAML
front matter (delimited by `---` lines, like Jekyll/Hugo) whose keys are the
element's fields **except** `source` and `body`, followed by the Markdown
body verbatim. `source` is never authored — the loader sets it to the path
relative to the store root. Records with no meaningful prose (`Component`,
`Seam`, `Milestone`, most `Story`s) simply have an empty body; the format
stays uniform rather than branching per kind, because a codec that has to
know which kinds get bodies is the kind of special-casing this project's own
`CLAUDE.md` says to avoid.

`system.yaml` and `layout.yaml` are plain YAML, no front-matter split — they
are true singletons, there is no filename-from-slug problem, and giving them
a Markdown body nobody will read is unearned ceremony.

If a task below needs to deviate from this (a strong reason turns up while
implementing `codec` or `load`), the deviation belongs in that task's own
PR description, not a silent divergence — and consider whether it's worth an
ADR once `.absicht/decisions/` exists to hold one (see
[`06-fixtures.md`](06-fixtures.md) and the Dogfooding section of
`CONTEXT.md`).

## Identity

`ab new KIND SLUG` generates `id = f"{kind}:{slug}"` — deterministic from the
slug, not a UUID. `SLUG` must already satisfy the `Slug` pattern in
`models.py` (`^[a-z0-9][a-z0-9-]*$`); a command that gets an invalid slug is a
`USAGE` error, not a library concern to swallow. Criterion ids
(`story:x#ac-1`) are only ever generated when a story's acceptance criteria
are authored, and are out of scope for `ab new` (see the `new` spec — it
lists `component seam data requirement nfr story decision rejection question
milestone external`, not criteria).

## JSON output

Every command's `--json` / `--format json` output is a single JSON object
with `"schema_version": SCHEMA_VERSION` at the top level (import from
`absicht.models`), plus command-specific fields. This is what
`docs/spec/cli.md`'s closing note means by *"`--json` output is versioned and
additive... a field never changes meaning — it gets deprecated and a new one
appears."* Don't invent a second envelope shape per command.

`--json` vs `--format`: see
[ADR-0001](../adr/0001-json-on-every-command.md) and the `Notes` section of
`cli.md`. Where a command has both, an explicit `--format` wins; `--json`
selects the `json` member of `--format` only when `--format` was left at its
default. `click.core.ParameterSource.DEFAULT` is how you tell "left at
default" from "explicitly passed the default value" — ADR-0001 already names
this; don't reopen it, implement it.

## Exit codes

`absicht.cli._common.ExitCode` is already defined and is the contract:
`OK=0`, `FINDINGS=1`, `USAGE=2`, `INTERNAL=3`, `SCHEMA_MISMATCH=4`. The
distinction that matters for every task producing a report (`check`,
`verify`): **`FINDINGS` is a true statement about the design or the diff**,
`USAGE` is a broken invocation, `INTERNAL` is a bug in `ab` itself. Never use
`INTERNAL` for "the design has a problem" — that's what makes `1` vs `2` a
signal CI can act on.

## `absicht.findings` (used by `check` and `verify`)

Both `ab check` and `ab verify` produce a flat list of findings against a
severity scale (`error` / `warn` / `info`, matching
`absicht.cli._common.Severity`) and both support `--format {text,json,sarif}`
and `--strict` (warnings become errors for the exit-code decision, not for
the finding's own severity field). Build this once, in
[`04-findings.md`](04-findings.md), rather than twice.

## Touching `tests/test_cli.py`

`tests/test_cli.py` currently asserts, for **every** documented command, that
invoking it exits `INTERNAL` with `"not implemented yet"` on stderr and
nothing on stdout (`test_command_parses_its_arguments_and_reports_no_body_yet`,
parametrized over the `SURFACE` dict). The moment a task gives a command a
real body, that command's entry must come out of the "not implemented"
parametrization and the surface flag-presence test
(`test_command_offers_every_documented_flag`) must stay — it's still true
that the command should offer every flag `cli.md` documents. Don't touch
`SURFACE` entries for commands you didn't implement; don't leave a landed
command's entry asserting `INTERNAL`.

## Workflow (from `AGENTS.md` / `CLAUDE.md`, repeated here so tasks can
reference it instead of re-quoting it)

- Tests first, own commit; implementation, own commit — so a reviewer can see
  the test wasn't written to fit the code.
- `./scripts/verify.sh fast` while iterating; `./scripts/verify.sh` (the full
  suite) before the final commit of a task. It must be clean.
- Run `./scripts/verify.sh mutation` if you touched tests in `model/`,
  `check.py` or `packet.py` once those are scoped in `[tool.mutmut]` — it's
  not in the default suite but it's the check that tells you whether a test
  asserts anything.
- Smoke tests and regression tests for feature deletions are not wanted.
  Tests should be focused. Comments explain the non-obvious *why*, not the
  *what* — see `AGENTS.md`.
- Commit often, in self-contained slices; always finish with a commit.

## Fixtures

Several tasks below need a store to run against before there's a real one.
[`06-fixtures.md`](06-fixtures.md) builds four small ones under
`tests/fixtures/systems/` (clean / brownfield / broken / composite) —
`verification.md` calls these *"the main safety net for this repo, ahead of
unit tests."* Tasks that need example data should use those fixtures rather
than inventing ad hoc ones per test file, so the same four systems accumulate
coverage instead of forty slightly-different toy stores.
