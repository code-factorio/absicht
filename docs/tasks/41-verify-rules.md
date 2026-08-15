# 41 — `ab verify`: rule bodies

## Depends on
[40-verify-core.md](40-verify-core.md).

## Spec
> Checks: the diff touched only components in scope; nothing marked
> `out_of_scope` was built; nothing was built on an `unknown` without a
> recorded decision; every seam in scope has a contract test that runs;
> every `done_when` criterion has something verifying it; scenario files
> are unmodified against the sealed digest; step definitions contain
> assertions.
>
> — [`../spec/cli.md`](../spec/cli.md#ab-verify)

Seven checks, seven rule functions against `VerifyContext` from
[`40-verify-core.md`](40-verify-core.md). Consider splitting *this* task
further across implementers by rule — they're independent of each other —
but they share enough context (all read the same `Packet` shape and diff)
that one task file covering all seven, done by one implementer who reads
the packet model once, is likely more coherent than seven near-identical
task files. Judgement call for whoever picks this up; split at commit
boundaries (one commit per rule) even if not across separate task files.

## What to build

Add to `src/absicht/verify.py`:

1. **`verify/scope`** — every file in `ctx.diff` maps to a component in
   `ctx.packet`'s full-fidelity elements (via each `Component.
   implemented_by` path prefixes, matched against the repo(s) in
   `--repo`). A changed file that maps to no in-scope component is a
   `Finding`.
2. **`verify/out-of-scope`** — a changed file mapping to a component whose
   packet-time `state` was `out_of_scope` (only meaningful if such a
   component is even present in the packet at any fidelity — decide whether
   an `out_of_scope` component appears in the packet at all, or whether its
   absence *is* the enforcement mechanism and this rule is instead "a
   changed file maps to no known component, full stop," folding into rule
   1 — read `31-packet-assembly.md`'s fidelity rules again before deciding
   these are actually two distinct rules).
3. **`verify/unknown-basis`** — a changed component whose packet-time
   `state` was `unknown` *and* no `Decision` in the packet's `must_hold` (or
   newly present, if the packet allows growth — probably not, packets are
   sealed) covers it. This is checking that the agent didn't quietly invent
   an answer to an `unknown` without it being recorded as a `Decision` —
   the mechanism the README's state table promises: *"Ask, spike, or mark
   blocking. Never invent."*
4. **`verify/contract-tests`** — every `Seam` in scope (packet-time, full
   fidelity) names something in `verified_by`, and that something
   corresponds to a test that actually exists and runs in `--repo` (a file
   path check plus, ideally, actually invoking the test runner — decide how
   deep "runs" goes; running arbitrary repo test suites from inside `ab
   verify` is a real design decision with sandboxing/trust implications,
   worth flagging explicitly rather than deciding silently — the safer
   first implementation is "the named test file exists and contains
   something that looks like a test," with actually *executing* it as an
   explicit, separately-decided follow-up).
5. **`verify/done-when`** — every `CriterionId` in the packet's
   `done_when`/`criteria` set has either a passing structural/measured
   check or a Gherkin scenario with a step definition that references it
   (searching `--repo` for the criterion id string in step-definition
   source is a pragmatic first pass; note the limitation).
6. **`verify/scenarios-unmodified`** — recompute
   `absicht.gherkin.scenario_digest` over the `.feature` files as they
   exist in `--repo` now, compare against `ctx.packet_lock.
   scenarios_digest`. Mismatch is a `Finding` — this is literally what
   sealing exists for.
7. **`verify/step-assertions`** — step definition files (found the same way
   rule 5 finds them) contain at least one assertion (`assert`, a testing
   framework's assertion call — this will be language/framework-specific
   since `--repo` is an arbitrary implementing repo, not necessarily
   Python; keep the detection heuristic simple and named as a heuristic in
   its `--explain` text, don't oversell its precision).

## Out of scope

- Executing the implementing repo's test suite for real (rule 4) is, per
  the note above, a decision to make explicitly and probably defer — land
  the existence check first, arrange the code so "actually run it" is an
  additive change, not a rewrite.

## Tests

- One fixture pair per rule: a sealed packet + a small fake `--repo` diff
  that trips the rule, and one that doesn't — same "fixture that trips it
  and one that doesn't" discipline `verification.md` asks of `check`'s
  rules, applied here too.
- An end-to-end run against a packet sealed from `tests/fixtures/systems/
  clean/`'s milestone and a `--repo` fixture built to satisfy every rule:
  `OK`, empty report.

## Definition of done

- Every rule id registered with an `--explain`-able description (reusing
  whatever `RuleCatalog` [`04-findings.md`](04-findings.md) built).
- `tests/test_cli.py`: `verify` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
