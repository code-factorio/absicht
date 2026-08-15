# 06 — Golden fixture systems

## Depends on
[00-conventions.md](00-conventions.md), [01-codec.md](01-codec.md) (for the
on-disk shape these need to be written in).

## Goal

`verification.md` ranks this the single highest-value check in the whole
gate — ahead of unit tests: *"Golden tests over fixture systems are the main
safety net, not unit tests."* Four small, hand-authored `.absicht/` stores
under `tests/fixtures/systems/`, each exercising a different shape of design,
that every later task (`load`, `resolve`, `check`, `build`, `packet`,
`render`) tests against instead of inventing its own toy data. This task
produces the *data*; it doesn't snapshot anything yet (there's nothing to
build/render/check until later tasks land) — but structure it so that when
those land, `syrupy` snapshot tests slot in against exactly these four
without rewriting them.

## What to build

`tests/fixtures/systems/`:

- **`clean/`** — small but complete: a `system.yaml`, 2-3 requirements each
  `realized_by` a component, 2-3 components with `contains`/`consumes`/
  `provides` relationships forming a real (small) graph, one seam between two
  of them, one data entity, one story with 2 behavioural acceptance criteria
  and one structural one, one accepted decision with a real rationale body,
  one milestone selecting a subset of the above. Every element `specified` or
  `constrained`. This is the "everything works, nothing to flag" case —
  `ab check` against it should be clean at every severity.
- **`brownfield/`** — mostly `observed` state, per README's own description
  of what brownfield honestly looks like: components with `observed` state
  and no rationale, at least one `unknown` with no owner (a real gap `ab
  gaps` should surface), a couple of orphaned elements nothing points at.
  This should *not* be clean under `ab check` — it should produce warnings
  (state/ownership policy findings), not errors, since brownfield is "an
  honest reading, not a failed one" (README's words).
- **`broken/`** — deliberately invalid, one fixture per failure family the
  checker needs to catch: a dangling ref (points at an id that doesn't
  exist), a cycle in `contains`, a criterion not anchored to its parent story
  (this one may not even parse — `Story`'s own validator catches it at load
  time; if so, note that in a comment and make sure it's still exercised, at
  the `load`/`codec` layer rather than `check`), a `one_way` decision with no
  rationale body, an `unknown` with no owner, an expired `external`
  assumption. One clearly-named subdirectory or clearly-commented section per
  case, so a later `check` task can point `--rule X` at exactly the case that
  should trip it and the case that shouldn't — `verification.md`'s
  *"per-rule coverage... every validation rule needs a fixture that trips it
  and one that does not"* rule applies here.
- **`composite/`** — multi-repo: `system.yaml` with 2+ `units`, at least one
  `external`, a seam whose `provider` is in one unit and `consumers` in
  another, to exercise the multi-repo path `status`/`verify --repo`/`marker`
  will need.

## Out of scope

- No snapshot files yet (`__snapshots__/`) — those get created by the tasks
  that actually build/render/check, against these fixtures, using `syrupy`
  (`assert result == snapshot`, `pytest --snapshot-update` once reviewed).
  Don't pre-guess the shape of an artifact that doesn't exist yet.
- Don't make these exhaustive of every field on every model — small and
  purposeful beats comprehensive. Each fixture exists to make one class of
  test possible; if a field isn't exercised by any planned test, leave it at
  its default.

## Tests

This task's own test is that [`02-load.md`](02-load.md) (once landed) loads
all four without crashing and reports the expected `LoadError`s for `broken/`
and none for the other three — but that assertion lives in `02-load`'s test
file, not here. This task's deliverable is the fixture files themselves,
reviewed by hand for being genuinely representative of the four shapes
described above (a `clean/` fixture that's secretly missing a rationale body
defeats the point).

## Definition of done

- Four directories exist under `tests/fixtures/systems/`, each a valid
  `.absicht/` tree per [`00-conventions.md`](00-conventions.md)'s file
  format (except `broken/`, deliberately).
- A short `tests/fixtures/systems/README.md` (or a module docstring in
  whichever test file first consumes them) explains what each fixture is for
  and which specific defects `broken/` contains, so a later task doesn't have
  to reverse-engineer the intent from the YAML.
- `./scripts/verify.sh` clean (this task adds no source code, but don't skip
  the check — a stray file elsewhere shouldn't ride in unnoticed).
