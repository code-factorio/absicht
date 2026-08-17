# Dogfooding the first store: what ab could not do

On 2026-08-17 absicht's own design moved into `.absicht/` — ~120 elements
authored from `docs/spec/cli.md`, `docs/spec/ABSICHT-MODEL-ADDENDUM.md`,
README, CONTEXT, `docs/tasks/` and `.rohrpost/tickets.jsonl`, then driven
through every command. CONTEXT.md predicted this would be the most
informative test in the repo. It was: two defects are already fixed on
main, and the list below is the rest of what the run surfaced.

The store itself is the input now: `ab check` against it is the dogfood CI
job `requirement:dogfood-in-ci` asks for.

## Defects found, fixed on main

1. **The trace walk was exponential, and the site OOMed a real machine.**
   `trace_paths` enumerated every simple path in both directions; a dense
   store holds exponentially many (this store: **more than five million
   from a single requirement**, 121 elements). `ab render`'s traceability
   page runs one trace per requirement and took the machine to 8 GiB
   resident, swapping, killed by hand. Fixed by a path budget spent in
   deterministic order plus a `truncated` flag spelled everywhere
   `cycle_hit` is; the site page takes a 50-path share
   (`decision:trace-answers-are-bounded`). The fixtures were too small and
   sparse to ever meet it.
2. **`ab status` reported every `done_when` vacuously met.** The claim
   scan's store-skip compared git's absolute paths against the caller's
   relative `--store` spelling, so the skip never fired and the store
   claimed its own criteria. The tests passed only because they spelled
   `--store` absolutely. Fixed by resolving the skip once
   (`0056f06`).

## Friction, by command

- `ab init` refuses an existing `.absicht/` that holds only the gitignored
  `build/` run store. The help says `--force` is for a store "that has no
  elements yet" — this was that case, but the refusal counted `build/`.
  Any repo that ran `ab packet` before authoring hits it.
- `ab new` cannot set kind-specific required fields (`external_kind`,
  `style`, `resource_kind`, `attribute`): the scaffold picks a placeholder
  (`external_kind: service`) and marks it with an HTML comment. Nothing
  later checks the placeholder was replaced — a store of placeholders
  checks green. Either flags for these fields or a check rule for
  leftover placeholders would close it.
- `ab note` writes bodies without a trailing newline, so the repo's own
  pre-commit hook fails on ab's own output (five note files fixed by the
  hook during the store's first commit).
- `ab note promote` takes no `--title`/`--state`/`--owner` (`ab new` has
  them) and drops the note's body: the promoted element starts as
  `title: <slug>` with an empty body, and the argument that justified it
  lives only in the note file.
- No upward store discovery: any command run from a subdirectory of the
  repo fails with "no store". Git-style walking to the repo root is the
  convention every other tool here follows.
- `ab packet` refuses a milestone with empty scope ("nothing an agent may
  touch"). Correct for code slices, but it means non-code slices cannot be
  packeted at all: the slice that authors the store's own elements has no
  components to name (the packet-first flow cannot bootstrap a store —
  `milestone:dogfood-store` records this), and step 0 — the project's own
  falsification milestone, "a text editor and nothing else" — is equally
  unpacketable. Any slice whose deliverable is packets, docs or a
  measurement has no packet.
- A packet sealed with the default `--format md` **cannot be read back by
  `ab verify`**. The default hand-off path is broken unless the caller
  knows to seal `--format json`. Either verify reads md packets or sealing
  md should warn it is unverifiable.
- `ab verify --packet` accepts the lock file path; the two-packet error
  lists lock paths as the choices; the *directory* form is refused with
  "no sealed packet there". Three spellings, one works.
- `verify/scope` flags `tests/test_render.py` as leakage: tests map to no
  component, and `implemented_by` has no convention claiming them. Every
  real code change touches tests, so every verify run errs until a
  convention exists (tests under the component's `implemented_by`, or a
  tests exemption).
- `verify/scenarios-unmodified` hashes `.feature` files it finds in the
  repo — including generated ones under `.absicht/build/packets/<other
  milestone>/`. The digest of an unrelated older packet fails the run.
  Gitignored build output should be outside the scan.
- Nothing documents how a pytest test claims an observation or a
  criterion: `verify/observations` reported all ten must-not-break
  observations `no_check` although the suite tests several of them,
  because nothing references `behavior:…#obs-N` as a string. The
  addendum's open question 3 (evidence hints) is this, materialized. A
  claiming convention — or at least a documented one-liner pattern in test
  docstrings — is missing.
- `ab diff REF_A REF_B` against a revision where no store exists fails
  with "system.yaml is missing: a store needs exactly one System element"
  — phrased as though the current store were broken, with no hint which
  side lacks a store.

## The adversarial review

After authoring, an eight-agent review (four finders, one skeptic per
dimension, each finding checked against the cited files) compared the store
to `cli.md`, the addendum, README + CONTEXT, and the tasks/tickets graph.
Twenty-three findings survived refutation. What it caught in the store is
fixed in the same commit as this document:

- `requirement:verify-returned-work` had dropped cli.md's qualifier —
  "built on an `unknown` **without a recorded decision**" — silently
  asking for a stricter rule than the code implements.
- One observation was invented: obs-4 claimed verify requires a recorded
  packet issuance, which neither spec nor code says. Downgraded to a
  `should` stating what is actually true.
- `component:runstore` sat in step 3's scope although the addendum built
  it, after every step-3 ticket closed; and the addendum's scope omitted
  `cli` and `new`, which its own ticket r1z4pk changed.
- Two `depends_on` edges were missing (step 4 ← step 2, via tasks 42/43's
  dependency on task 20; addendum ← step 4, via task 59's on 40/41) —
  both promoted from ticket `blocked_by` edges the reviewer derived.
- The 0x foundations wave belonged to no milestone and its six ticket ids
  appeared nowhere; `milestone:foundations` now holds them.
- CONTEXT "Decided" bullets with no element (identity-carries-no-location,
  structured-records-prose-where-reasoning-resists, capture-on-touch), the
  fourth "not decided" item (does the graph earn its cost), the per-state
  agent postures, the unit definition, embedded-mode status and optional
  markers, and four of README's "Not this" refusals all got homes.

What it caught in the **sources** (stale against code, left for their
owners): the README status table and the tasks README's "nothing behind it
yet" snapshot; the addendum's `kind:` field (implemented as
`resource_kind`), its `model/`-msgspec table and its §7 "only Question
carries an owner" claim; cli.md's trace section claiming `truncated` "in
every format" when mermaid carries no note, and its unconditional "each
run is recorded" — both corrected in this change; and the README shape
tree, which folds `non_functionals/` into `requirements/` and omits six
existing kind directories.

## Model expressiveness: what still has no home

The review's confirmed gaps, plus the run's own — after the fixes above:

- **`DataEntity` field names cannot carry underscores** — `FieldSpec.name`
  is a `Slug`. absicht cannot spell its own `schema_version`, `packet_id`,
  `commit_sha`; the store says `schema-version` and the mapping lives in a
  body. The rule that guards element ids is applied to a place where the
  code's own spelling is snake_case.
- **No maintainability or determinism `QualityAttribute`.** The layer-stack
  contract and the format-swappability argument — the repo's most
  load-bearing quality scenarios — have no NFR field; determinism was
  squeezed into `operability`, the layer stack lives in a decision body.
  The eight-value enum is too narrow for the project that defines it.
- **Behaviors realize only requirements.** An NFR cannot have a behavior;
  `nfr:byte-identical-build` wanted one and `requirement:build-artifact`
  carries it instead.
- **No home for sibling projects or the ecosystem boundary.** "Where this
  sits" (rohrpost holds work, vermittlung holds interpretation, each runs
  alone, none is a plugin of the others), the design-layer-is-not-the-
  planner boundary, and the Vermittlung-as-second-victim caveat are
  neither external, unit nor component. They survive as README and
  CONTEXT prose only.
- **No home for ticket linkage.** Milestones ↔ rohrpost tickets is a
  many-to-many the run recorded as ticket ids inside milestone bodies.
  Rohrpost owns work, but a pointer convention would keep the store
  answerable ("which tickets delivered this step?").
- **Milestones cannot say they landed.** Steps 1–4 are complete (all
  tickets done) but no field says so: `state` is completeness of the
  *specification*, lifecycle is behaviors-only (addendum open question 2,
  materialized here). The gaps worklist treats a finished milestone's
  unmet `done_when` identically to an unfinished one's.
- **Editorial criteria cannot close.** `done_when` criteria like "every
  kind has an instance" have no mechanical check and no path to one —
  honest as permanent findings, but the model invites criteria verify can
  never green.
- **The README status table was stale against the tickets** (addendum
  "proposed" while tasks 51–60 are done; steps 2–3 "in progress" while
  their tickets closed). The store held the true states before the README
  did — nothing projects store → README, so the table stays
  hand-maintained and drifts. `note:qwkiri` captured it; this change also
  edits the table by hand.
- **The CLI flag surface has no structural home.** The most detailed part
  of `cli.md` — `--quiet`/`--verbose`/`--no-color` semantics, `--store`
  resolution order and `$ABSICHT_STORE`, check's `--rule`/`--severity`/
  `--changed-only`/`--diff-base`/`--explain`, render's `--serve`/
  `--overlay`, layout's `--seed`, packet's `--features-dir`, new's
  `--print`/`--edit` — survives only as prose fragments inside requirement
  bodies. The model has no command or flag kind, and components carry no
  flag contract. Either the model grows one or this stays prose forever.
- **Validation-rule contracts live only in code.** The rule inventory and
  its severity asymmetries (`behavior-needs-observations` an error,
  `requirement-needs-behavior` a warning) appear in no element;
  `requirement:validate-store` names rules in prose without severities.
  `data:finding` describes the output, not the rules.
- **Task-level edges and waves are coarser than reality.**
  `Milestone.depends_on` is a whole-block edge; the tasks graph's
  cross-block edges (42 → 20, 59 → 40/41) had to be promoted by hand and
  two were missed until the review, and the within-block parallel waves
  have no field at all.
- **"Parked pending a condition" is not a state.** The four `9x` tickets
  were dropped with a revisit trigger — "until every numbered task below
  90 has landed" — which is now true and nothing surfaces it. Not
  `out_of_scope`, not a rejection (they are deferred, not killed); the
  trigger survives only in the ticket log.

## What worked

`ab check` caught exactly what it should on first contact: prose with a
colon breaking YAML, a stray extra key, dangling refs, an ownerless
unknown — each finding named its file. The two deliberate warnings on
`requirement:dogfood-in-ci` (no realizer, no behavior) surfaced in `ab
gaps` exactly as a worklist should. Build and site proved byte-identical
across runs and `PYTHONHASHSEED`. The packet's derived must-not-break list
was right without being authored. `ab diff` answered in elements. `ab
status` refusing `--behind-only` in embedded mode with a stderr
explanation is the right shape of no-op. And the defects above were all
found by the store's own density — the fixtures never reached them.

## Recommended next slices

1. The CI dogfood job (`requirement:dogfood-in-ci`): `ab check` against
   this store on every push. It exists now; wire it.
2. Verify's claiming convention: how a test names what it checks.
3. md-sealed packets readable by verify, or md sealing warns.
4. Tests under `implemented_by` scope, and build output outside verify's
   scenario scan.
