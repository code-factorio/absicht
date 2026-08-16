# Implementation tasks

Every file in this folder except this one is a **self-contained prompt** for
handing to one implementing agent: goal, spec excerpt, concrete deliverables,
out-of-scope, tests, definition of done. They exist so `absicht`'s CLI surface
— scaffolded as signatures first, built out command by command since — can be
implemented by many agents or by one agent working sequentially, without each
of them re-deriving the same context from scratch. The `5x`/`60` block covers
the [model addendum](../spec/ABSICHT-MODEL-ADDENDUM.md): behaviors,
resources, observations, notes, and the run store.

Derived from [`../spec/cli.md`](../spec/cli.md) (the surface), the project
README and [`CONTEXT.md`](../../CONTEXT.md) (the why), `AGENTS.md` /
`CLAUDE.md` (house rules), [`../maintainers/verification.md`](../maintainers/verification.md)
(the gate), `pyproject.toml` (the layer contract), and the current state of
`src/absicht` — models done, CLI scaffolded, nothing behind it yet.

## Read first

**[`00-conventions.md`](00-conventions.md)** — every other task assumes it.
It pins the things that would otherwise get re-decided differently by every
task: the module layer stack, the on-disk file format, id rules, the JSON
output envelope, exit codes, and the repo's test/commit workflow. Hand it to
an agent alongside whichever numbered task it's building.

## Order

Files are numbered by dependency, not by the order commands appear in
`cli.md`. Lower numbers must land — merged, `verify.sh` green — before higher
numbers that depend on them start. Within a block, tasks are independent of
each other and can run in parallel once their dependencies are met.

| # | Task | Builds | Depends on |
|---|---|---|---|
| 00 | [conventions](00-conventions.md) | — (reading, not code) | — |
| 01 | [codec](01-codec.md) | `absicht.codec` | 00 |
| 02 | [load](02-load.md) | `absicht.load` | 00, 01 |
| 03 | [resolve](03-resolve.md) | `absicht.resolve` | 00, 02 |
| 04 | [findings](04-findings.md) | `absicht.findings` | 00 |
| 05 | [git](05-git.md) | `absicht.git` | 00 |
| 06 | [fixtures](06-fixtures.md) | `tests/fixtures/systems/*` | 00, 01 |
| 10 | [init](10-init.md) | `ab init` | 00, 01 |
| 11 | [new](11-new.md) | `ab new` | 00, 01, 03 |
| 12 | [check: schema layer](12-check-schema.md) | `absicht.check` (schema) | 00, 02, 04 |
| 13 | [check: integrity layer](13-check-integrity.md) | `absicht.check` (integrity) | 00, 03, 04 |
| 14 | [check: policy layer](14-check-policy.md) | `absicht.check` (policy) | 00, 03, 04 |
| 15 | [check: CLI](15-check-cli.md) | `ab check` | 12, 13, 14, 05 |
| 16 | [schema command](16-schema-cmd.md) | `ab schema` | 00 |
| 17 | [migrate](17-migrate.md) | `ab migrate` | 00, 02 |
| 20 | [build](20-build.md) | `ab build`, `absicht.build` | 00, 03, 05 |
| 21 | [show](21-show.md) | `ab show` | 00, 03, 20 |
| 22 | [list](22-list.md) | `ab list` | 00, 03, 20 |
| 23 | [gaps](23-gaps.md) | `ab gaps` | 00, 03, 20 |
| 24 | [trace](24-trace.md) | `ab trace` | 00, 03, 20 |
| 25 | [layout](25-layout.md) | `ab layout` | 00, 03 |
| 26 | [render: site](26-render-site.md) | `ab render` (pages) | 20, 21, 22, 23, 24 |
| 27 | [render: diagrams](27-render-diagrams.md) | `ab render` (diagrams) | 25, 26 |
| 30 | [gherkin](30-gherkin.md) | `absicht.gherkin` | 00, 03 |
| 31 | [packet: assembly](31-packet-assembly.md) | `absicht.packet` | 00, 03, 04 |
| 32 | [packet: CLI](32-packet-cli.md) | `ab packet` | 31, 30, 05 |
| 33 | [features](33-features.md) | `ab features` | 30, 03 |
| 40 | [verify: core](40-verify-core.md) | `absicht.verify` scaffolding | 00, 04, 05, 31 |
| 41 | [verify: rules](41-verify-rules.md) | `ab verify` rule bodies | 40 |
| 42 | [status](42-status.md) | `ab status` | 00, 03, 05, 20, 44 |
| 43 | [diff](43-diff.md) | `ab diff` | 00, 04, 05, 20 |
| 44 | [marker: sync](44-marker-sync.md) | `ab marker sync` | 00, 01, 03 |
| 45 | [marker: check](45-marker-check.md) | `ab marker check` | 44 |
| 46 | [marker: stamp](46-marker-stamp.md) | `ab marker stamp` | 44, 05 |
| 50 | [addendum conventions](50-addendum-conventions.md) | — (reading, not code) | 00 |
| 51 | [model: behaviors, resources](51-model-behaviors-resources.md) | `models.py` additions, `schema/` | 00, 50 |
| 52 | [store wiring](52-store-wiring.md) | codec/load/resolve/build for new kinds, fixtures | 50, 51 |
| 53 | [notes](53-notes.md) | `absicht.notes`, `ab note` | 50, 51 |
| 54 | [check: addendum rules](54-check-addendum-rules.md) | `absicht.check` additions | 50, 52, 53 |
| 55 | [addendum query surface](55-addendum-query-surface.md) | `ab new/list/show/gaps/trace` for new kinds | 50, 52 |
| 56 | [derived scope, composition](56-derived-scope-composition.md) | `absicht.resolve` derivations | 50, 52 |
| 57 | [packet: behaviors](57-packet-behaviors.md) | `absicht.packet` additions | 50, 56, 31, 32 |
| 58 | [run store](58-run-store.md) | `absicht.runstore` | 50 |
| 59 | [verify: observations](59-verify-observations.md) | `absicht.verify` additions | 50, 57, 58, 40, 41 |
| 60 | [addendum render](60-addendum-render.md) | site pages, diagrams, note inbox | 50, 53, 56, 26, 27 |
| 90 | [later: extract](90-later-extract.md) | `ab extract` | not started |
| 91 | [later: import](91-later-import.md) | `ab import` | not started |
| 92 | [later: mine](92-later-mine.md) | `ab mine` | not started |
| 93 | [later: serve](93-later-serve.md) | `ab serve` | not started |

## For an orchestrator

- Treat each file as one unit of work for one agent (or one agent-turn).
  Foundations (`00`–`06`) gate everything; do them first, in the listed
  order where a dependency arrow says so, otherwise in parallel.
- The `1x` (author/validate), `2x` (build/query), `3x` (handoff), `4x`
  (verify) blocks roughly track `cli.md`'s own steps and can be built as four
  waves, but a task should not start before every task in its `Depends on`
  column has landed and `./scripts/verify.sh` is green on `main`.
- The `5x`/`60` block implements the model addendum. `50` is reading, like
  `00` — hand both to every agent working a 51–60 task. `51 → 52` is the
  spine; `53`, `55`, `56`, `58` fan out behind `52` (or `51`/`50` where the
  table says so) and can run in parallel; `54`, `57`, `59`, `60` close over
  them. `57` and `59` additionally wait on the pre-addendum packet (`31`,
  `32`) and verify (`40`, `41`) tasks; `60` waits on render (`26`, `27`).
- The `9x` block is explicitly **not scoped** — see each file. Don't assign
  these until the numbered tasks above are done and dogfooded; the README's
  own status table calls them "later" for a reason (nothing before them has
  been falsified yet).
- Every task ends the same way: tests first (own commit), implementation
  (own commit), `./scripts/verify.sh` clean. See `00-conventions.md` for the
  full house rules — don't repeat them per task, reference them.
- When a task adds a new `absicht.*` module, updating the layer list in
  `pyproject.toml`'s `[[tool.importlinter.contracts]]` is part of that task,
  not a follow-up. A layer that exists and isn't listed makes the contract
  silently stop covering it.
