# Verification

One rule: **run `./scripts/verify.sh` before you commit anything you intend to
push.** Everything below is detail.

```bash
./scripts/verify.sh            # every gate CI enforces, ~6s
./scripts/verify.sh quick      # the pre-commit subset, well under a second
./scripts/verify.sh fast       # quick, plus the checks that answer in seconds
./scripts/verify.sh types test # one or more checks by name
./scripts/verify.sh all        # adds mutation testing
make verify                    # the same, if you prefer make
```

A failing check does not stop the run: one invocation lists everything that is
wrong, and the summary ends with the command that re-runs only the failures.

The script is the single definition of every check. The git hooks call it, CI
calls it, the Makefile calls it, and none of them add a flag of their own — so
"it passed locally" and "it passed in CI" cannot mean different things. If you
add a check, add it to `scripts/verify.sh` and to the suite lists at the top of
that file, and it appears everywhere at once.

## The checks

| Check | Tools | Looks for |
|---|---|---|
| `format` | ruff format | formatting, in `src`, `tests` and `scripts` |
| `lint` | ruff check | the lint rule set in `pyproject.toml` |
| `types` | mypy | type errors |
| `imports` | import-linter | modules importing across the layer boundaries |
| `deps` | deptry | undeclared and unused dependencies |
| `security` | bandit | injection, weak crypto, unsafe subprocess use |
| `complexity` | xenon | cyclomatic complexity above the ceiling |
| `quality` | pyscn | dead code, circular imports, clones |
| `test` | pytest, hypothesis | the suite, and the coverage floor |
| `mutation` | mutmut | tests that execute code without checking it |

Suites nest: `quick` ⊂ `fast` ⊂ `full` (the default) ⊂ `all`.

## Why this gate is not Vermittlung's

Rohrpost and Vermittlung tuned this stack, and most of it was copied over
rather than re-argued. Three deliberate differences, all of them following
from the same observation: **the users of this repo are agents, and an agent's
failure mode is not carelessness, it is plausibility.** Code that looks
completely right, satisfies the type checker, and is wrong. Tests that assert
nothing. A happy path with the error branch quietly dropped.

**One type checker, not three.** Vermittlung runs mypy, ty and pyright because
they disagree and the disagreements are where the interesting bugs are. That
is true, and the marginal catch rate of the third is still tiny — while the
cost is three sets of ignore comments and three configs that drift, paid on
every push. mypy strict is the gate. pyright is configured in
`[tool.pyright]` for the editor's language server and is deliberately not run
by `verify.sh`. `ty` is not installed: pre-1.0 and not a blocker.

Agents are, in any case, good at satisfying types. The type checker is not
where this repo's risk lives.

**Mutation testing is the most valuable check here, not a nice-to-have.** It
is the only tool in the list that answers "do these tests assert anything",
which is exactly the artifact an agent produces when told to make coverage
green. It stays out of both git hooks and runs nightly.

**Diff coverage, not a repo-wide percentage.** A global threshold is a ratchet
that mostly teaches you to write tests for getters. New lines in a change must
be covered; that is unambiguous and it removes the easiest escape route. The
floor in `[tool.coverage.report]` is a guard against collapse, not the
coverage story.

Also dropped: `radon`. xenon is the enforcing half and the report was never
the thing that failed a build. Also added: `deptry`, which is small and
catches real drift.

## Thresholds, and which of them are ratchets

Some numbers are goals. Others are simply where the code stands today, set
there so that the next commit cannot make things worse. Raise a ratchet when
you improve the code behind it. Never lower one to make a branch pass.

Absicht has almost no code yet, so — unlike Vermittlung — none of these are
ratchets against existing debt. They are ceilings chosen in advance, and the
first thing to check when one starts firing is whether the number was wrong
rather than whether the code is.

| Threshold | Where | Today | Why that number |
|---|---|---|---|
| coverage ≥ 60% | `[tool.coverage.report]` | 85% | a floor against collapse; the real signal is diff coverage |
| diff coverage = 100% | `.github/workflows/ci.yml` | n/a | new lines in a change, on pull requests only |
| xenon max-absolute E | `scripts/verify.sh` | worst block is A (3) | loose on purpose: see below |
| xenon max-average A, max-modules B | `scripts/verify.sh` | A (2.0) | comfortable, and worth keeping |
| pyscn max-complexity 15 | `scripts/verify.sh` | nothing near it | loose on purpose; pyscn's default is 10 |
| mutation ≥ 45% | `MUTATION_FLOOR` in `scripts/verify.sh` | not yet armed | a starting guess, to be revised on first real data |

### Why the complexity ceilings are loose

Not debt — anticipation. `resolve` and `check` will legitimately have branchy
functions: "which shape is this" and "which of these seventeen rules does this
element violate" are the kind of code that gets complex honestly. A ceiling
tight enough to fire on those would be turned off within a month.

The ceiling is a smoke alarm, not a design tool. It is here because agents
grow functions rather than refactoring them, and a limit is a forcing function
they respond to. If it fires on `resolve.py`, read the function before
assuming the gate is right.

pyscn's clone detection is the part of `quality` that earns its keep.
Copy-paste-and-tweak is the signature move: duplicate the neighbouring
function rather than extend it, because that is locally safe and globally
corrosive. Expect it to have opinions about the record types, which will
genuinely resemble each other — the judgement call is the same one Vermittlung
makes about its adapters, and it goes the same way. Deliberately parallel
things are allowed to look parallel.

### The bandit exceptions

`[tool.bandit]` skips exactly one check: B101, because asserts here are
narrowing invariants and never input validation. Everything else runs at full
sensitivity.

Vermittlung skips four; three of those describe a bus that shells out to `rp`
and samples with `random`, and neither is true of this repo. If absicht ever
grows a subprocess call, the exception goes at the site as `# nosec <id>` with
a reason, not into the skip list.

### The import contracts

`[tool.importlinter]` holds one, **Absicht layers**: the stack from the model
up to the entry points, where a module may import anything below it and
nothing above.

This is the contract that matters most in this repo, and it is enforced from
the first commit rather than asserted in a document, because two later
decisions depend on it:

- the file format stays swappable, since nothing below `codec` knows how a
  record was spelled on disk;
- the core stays reusable behind a web or MCP surface, since nothing below
  `cli` knows it is being run from a terminal.

The full stack is written out as a comment above the contract in
`pyproject.toml`. Only the layers that currently exist are in the contract
itself — import-linter fails on a named module that is not there, and a
contract nobody can run is worse than no contract. **Add each layer to the
list in the same commit that creates the module.**

When it breaks, import-linter prints the offending chain. The fix is nearly
always to pass the thing in rather than to import it.

## Mutation testing

`mutmut run` exits zero however many mutants survive, so the threshold lives
in `scripts/mutation_score.py`: killed over killed-plus-survived, against
`MUTATION_FLOOR`. Mutants with no covering test and mutants that never
finished are excluded — they say something about coverage or about mutmut, not
about whether the tests can tell right from wrong.

The check is **scoped, and currently unarmed.** `MUTATION_SCOPE` in
`scripts/verify.sh` names `model/`, `check.py` and `packet.py`: the places
where a silent wrong answer is the entire failure mode. A packet that quietly
omits a `must_hold` ADR is exactly the bug that makes this product worthless,
and no other check in this file would see it. The renderer and the CLI are not
worth the runtime.

None of those modules exist yet, so `check_mutation` says so and returns
success. It arms itself the moment one of them lands — no configuration
change, no remembering. Until then, `pyproject.toml` also excludes
`__init__.py`, `__main__.py` and `cli.py`: a version constant and argument
plumbing, where a mutant survives or dies on Typer's behaviour rather than
ours.

Run `make mutation` yourself when you have changed tests, or when you want to
know whether a test asserts anything at all.

## The git hooks

```bash
uv run pre-commit install     # installs both hook types
```

- **pre-commit** runs `verify.sh quick` — format and lint, nothing else —
  plus the whitespace fixers. This budget is not negotiable. The moment a
  commit hook costs four seconds people reach for `--no-verify` and the whole
  mechanism is gone, and "commit often" is only advice you can follow if
  committing is cheap.
- **pre-push** runs `verify.sh types test`, that being the last point before
  anyone else, and CI, sees the work.

Note that this is a stage lower than Vermittlung, which runs the fast suite on
commit and the full suite on push. Everything slower — the import contracts,
complexity, pyscn — lives in CI, where it can fail in its own job with its own
name.

The fixers (end-of-file, trailing whitespace) modify files and fail the commit
when they do. Stage the fix and commit again.

## CI

`.github/workflows/ci.yml` has three jobs.

- `verify` runs `./scripts/verify.sh` on every pull request and every push to
  `main`. It installs with `uv sync --locked`, so a `uv.lock` that has drifted
  from `pyproject.toml` is a build failure.
- `diff-coverage` runs on pull requests only, and requires 100% coverage of
  the lines the change adds.
- `mutation` runs nightly and on demand, and keeps the survivor list as a
  build artifact.

Single Python version, no matrix. This is not a library and there are no users
to support.

## The checks that are missing on purpose

Absicht's own vocabulary applies to its own gate: incompleteness is a state,
not an omission. Four of the highest-value checks for this particular product
do not exist yet, because there is nothing for them to run against. They are
named in a comment at the top of `ci.yml` so they arrive as jobs rather than
as an afterthought.

Ranked by value per second of CI, the target gate is:

> golden fixtures > determinism > mypy > mutation on the core modules >
> dogfooding `ab check` on absicht's own `.absicht/` > everything else

Two of those five are already here. The rest:

**Golden fixtures** — the main safety net for this repo, ahead of unit tests.
Four small systems under `tests/fixtures/systems/`: a clean one, a brownfield
one that is mostly `observed`, one deliberately broken for the checker, and
one multi-repo composite. Snapshot the build artifact, a rendered page, an SVG
and a packet. `syrupy` is already a dev dependency for this.

**Determinism**, as its own job. Build twice from a clean checkout, diff the
artifacts, byte-identical or fail. The same for SVG output under a pinned
layout — stable layout is the entire reason the diagrams are worth having, and
a diagram that reshuffles on every regeneration never builds spatial memory.
Vary `PYTHONHASHSEED` so dict-ordering leaks surface.

**Dogfood** — `ab check` against absicht's own `.absicht/`. If your own design
fails your own validator, that is the most informative test in the repo. The
caveat worth remembering: absicht's own store will be pristine, which is the
least representative input it will ever see. Vermittlung is the better second
victim.

**Schema migration** — load the previous schema version's fixtures and migrate
them. From the day the schema exists, because it will change constantly in the
first six months.

And one that is not a CI job but a rule: **per-rule coverage in the checker.**
Every validation rule needs a fixture that trips it and one that does not.
That is a real completeness claim, which a percentage never is.

## What none of this checks

Every tool above asks "is this code well-formed". None of them asks "is this
the code we asked for", and that second question is the entire premise of the
project. The answer is `ab verify` — the counterpart to `ab packet`, run after
the agent, in the same CI job as everything else:

- Does the diff touch only components in the packet's scope?
- Does every seam in scope have a contract test that runs?
- Does each `done_when` have something that verifies it?
- Did the change touch anything `out_of_scope`, or build on something
  `unknown`?
- Did the watermark move without a reconciliation report?

Deterministic, cheap, and impossible for anyone who does not have the design.
It must run offline against a fetched packet — in CI, in somebody else's repo,
with the network locked down — which is why the verification logic belongs in
a package and never behind a server.

The generic gate keeps agents from writing bad code. `ab verify` keeps them
from writing the wrong code. Both are needed; only the second one is ours to
build.
