# Context

Standing context for anyone — human or agent — picking up `absicht`. The
README is the argument. This is what was decided on the way to it, what is
still open, and the reasoning behind the choices that are not obvious from the
code.

## Vocabulary

- **packet** — a bounded, machine-readable brief for one slice of work,
  assembled by walking the model. The unit of output, and the thing the whole
  project is a bet on.
- **unit** — anything with its own release cadence. Not anything with its own
  deployment. A library, a service, a component inside a monolith.
- **seam** — a boundary between units: contract, model, failure modes. The
  provider owns the contract, the consumer owns their expectations of it.
- **watermark** — `at` and `design_rev` in a repo's `.absicht` marker. Where
  the code caught up to, not what the code conforms to.
- **state** — the six-valued incompleteness of an element: `specified`,
  `constrained`, `delegated`, `unknown`, `observed`, `out_of_scope`. See the
  README table for the agent posture each one implies.
- **design store** vs **implementing repo** — the store owns composition and
  implementation references; a marker in an implementing repo is a discovery
  hint that `ab check` verifies against the store. The store wins.

`design` is ours. `structure` is derivable from code and mostly is not.

## Decided

- **Files first, build artifact second.** `.absicht/` is the authoring and
  review surface, because diffs, `git merge-file` and pull-request review are
  what keep the store honest when agents write to it. `ab build` folds the
  tree into one normalized JSON document; everything downstream consumes that
  and nothing else. Same shape as Rohrpost's log → tickets fold.
- **Structured records, prose only where reasoning resists fields.**
  Components, seams, data models, milestones and stories are pure structure.
  ADR context, NFR rationale and rejections keep a prose body, because an ADR
  whose context is `["performance", "vendor_lock_in"]` has thrown away the
  argument — and the argument is the non-derivable half this project exists to
  hold.
- **Schema in exactly one place.** pydantic models in
  `src/absicht/models.py` (an earlier draft said msgspec under `model/`;
  pydantic won). The validator, the JSON Schema in `schema/` and the
  reference docs are generated from them. Committing the JSON Schema gives YAML editors autocomplete and
  inline errors on `.absicht/` files, which is most of what an authoring UI
  would have bought. Every artifact carries `schema_version`.
- **A library with a thin CLI over it, from the first commit.** Not a CLI to
  extract a library from later. No business logic in `cli.py`, no `print`
  outside the render layer, no `sys.exit` in the core, everything returns
  values. `--json` on every command from day one: agents are the primary
  consumer, the terminal is the secondary one. This is what makes the eventual
  web and MCP surfaces a week rather than a rewrite.
- **`ab` is the binary, `.absicht/` is the store**, sitting alongside
  `.rohrpost/`.
- **The store's location is a mode, and `.absicht` carries it.** A directory
  is embedded: the store lives in the repo it describes, which is where a
  single-repo project starts. A file is reference: the store is its own repo
  and the file is a marker pointing at it, which is where a composite ends up,
  because a ticket belongs to a codebase but a design belongs to a system and a
  system is a composition. `system.yaml` pins the units it composes, like a
  lockfile, either way. The modes are exclusive because the filesystem makes
  them so: one name is one directory entry.
- **Watermarks are hints, not pins.** They over-claim in practice — a merge
  stamps `M003` because the work was declared done — so the gap always reads
  smaller than it is. That is survivable because the watermark was never the
  only route to that code, and because it self-corrects on touch: the next
  packet against a component compares design to reality and the lie dies. What
  `ab status` computes is a fact about two commits, which is true regardless.
- **Capture on touch, never backfill.** Design truth accretes along the path
  of real work. A brownfield import that lands 90% `observed` is telling the
  truth, not failing.
- **Identity carries no location.** Components get extracted from monoliths
  into libraries into services. The ID survives the move.

## Deliberately not decided

- The smallest schema that still produces a useful packet. This is what step 0
  is for: write three packets by hand, notice which fields an agent actually
  used, and let the schema be the fold over that. **Do not start with the
  schema.**
- The context horizon. Selected scope at full fidelity plus one ring of
  neighbouring contracts is the hypothesis, not the answer. A packet for a
  component in a monolith that consumes three libraries and two vendors is the
  shape to design against.
- Files-first or server-first once several systems and several people are
  involved. The library does not care whether records came from files or from
  Postgres, which is the point — the question stays open.
- Whether the graph earns its cost at all. Step 2 is read-only projections
  precisely so that "do I actually look at these" gets answered before
  anything is made editable.

## Where this sits

Vermittlung decides what deserves attention. `absicht` says what is true and
what is permitted. Rohrpost holds what is being done about it. Each runs
alone; none is a plugin of the others.

The boundary to nail down before it matters: Vermittlung dispatches a planner
on `new_work`. The design layer is *not* that planner — it sits behind it as a
knowledge source. A planner that also owns truth becomes the centre of
everything.

## Why the gate looks like this

Copied from Vermittlung and Rohrpost, then cut, because absicht's risk profile
is different and because the users are agents.

An agent's failure mode is not carelessness, it is *plausibility*: code that
looks completely right, satisfies the type checker, and is wrong. Tests that
assert nothing. A happy path with the error branch quietly dropped. A function
that satisfies the signature and not the requirement. So the tools that catch
plausibility are worth more than the tools that catch sloppiness.

- **Mutation testing is the most valuable tool in the suite**, because it is
  the only one that answers "do these tests test anything". Scoped hard and
  run nightly.
- **Diff coverage, not repo-wide coverage.** New lines in a change must be
  covered. Unambiguous, and it removes the easiest escape route. Once the
  checker exists, every validation rule needs a fixture that trips it and one
  that does not — that is a real completeness claim, unlike a percentage.
- **Clone detection earns its keep.** Copy-paste-and-tweak is the signature
  move: duplicate the neighbouring function rather than extend it, because
  that is locally safe and globally corrosive.
- **One type checker.** The marginal catch rate of the third is tiny and you
  pay for it on every push, plus three sets of ignore comments and three
  configs that drift. mypy strict gates; pyright is what the editor runs.
- **Complexity as a smoke alarm, not a design tool.** Agents grow functions
  rather than refactoring, so a ceiling is a forcing function they respond to.
  But `resolve` and `check` will legitimately be branchy, so the ceiling stays
  loose.
- **Sub-second commit hooks.** The moment a commit hook takes four seconds
  people reach for `--no-verify` and the mechanism is gone.

And the layer this suite cannot provide: every tool above asks "is this code
well-formed", none asks "is this the code we asked for". That second question
is the entire premise of the project, and the answer is `ab verify` — the
counterpart to `ab packet`, run after the agent:

- Does the diff touch only components in the packet's scope?
- Does every seam in scope have a contract test that runs?
- Does each `done_when` have something that verifies it?
- Did the change touch anything `out_of_scope`, or build on something
  `unknown`?
- Did the watermark move without a reconciliation report?

Deterministic, cheap, and impossible for anyone without the design. When the
three step-0 packets get written, the verification gets written alongside each
one: a slice whose "done" cannot be stated mechanically was underspecified.

`ab verify` must run offline against a fetched packet, in CI, in somebody
else's repo. That keeps verification in a package rather than behind a server,
whatever the eventual web surface looks like.

## Ranked by value per second of CI

Golden fixtures > determinism check > mypy > mutation on the core modules >
dogfooding `ab check` on absicht's own `.absicht/` > everything else.

Two of those are not generic tooling and have to be built:

- **Golden tests over fixture systems** are the main safety net, not unit
  tests. Four small systems under `tests/fixtures/systems/`: a clean one, a
  brownfield one that is mostly `observed`, one deliberately broken for the
  checker, one multi-repo composite. Snapshot the build artifact, a rendered
  page, an SVG and a packet.
- **Determinism is an invariant with its own CI job.** Build twice from a
  clean checkout, diff the artifacts, byte-identical or fail. Same for SVG
  output with a pinned layout, since stable layout is the entire reason the
  diagrams are worth having — a diagram that reshuffles on every regeneration
  never builds spatial memory. Vary `PYTHONHASHSEED` so dict-ordering leaks
  get caught.

## Dogfooding

`ab check` runs against absicht's own `.absicht/` in CI. If your own design
fails your own validator, that is the most informative test in the repo.

The caveat worth remembering: absicht's own store will be pristine — every
component specified, every ADR deliberate — which is the least representative
input it will ever see. Vermittlung is the better second victim. It is
brownfield-ish, has real ADRs, spans a boundary with Rohrpost, and has open
spec questions that land as genuine `unknown`s rather than tidy ones.

## Order of work

Step 0 needs a text editor and nothing else. The gate and the schema come with
step 1 — putting them in first is the pleasant procrastination that makes a
project feel real before it has been falsified.

See the status table in the README for what each step contains.
