# 59 — Verify: observations — `checked`, `no_check`, `advisory`

## Depends on
[00-conventions.md](00-conventions.md),
[50-addendum-conventions.md](50-addendum-conventions.md),
[57-packet-behaviors.md](57-packet-behaviors.md),
[58-run-store.md](58-run-store.md),
[40-verify-core.md](40-verify-core.md) and [41-verify-rules.md](41-verify-rules.md)
— **landed first**; this extends `absicht.verify`.

## Goal

The addendum's answer to "did the agent do the work": for every observation
the packet carried, does *something* check it? This is coverage of
expectations, not execution of tests — the line that keeps absicht from
becoming a BDD framework is drawn in this task, so hold it.

## Spec

> Verification asks whether every `must` and `must_not` observation **has
> something checking it** — a test, an assertion, a metric, a log query —
> and reports three outcomes:
>
> | Result | Meaning |
> |---|---|
> | `checked` | Something verifies this observation, with evidence |
> | `no_check` | Nothing verifies it — the observation is unguarded |
> | `advisory` | It is a `should`; reported, never failed |
>
> `no_check` is the distinctive result […] absicht does not run checks and
> does not own assertions. The moment it does, it is a BDD tool with a
> design store attached, which is a different and much larger product.
>
> — [addendum §9](../spec/ABSICHT-MODEL-ADDENDUM.md#9-what-verification-does-and-does-not-do)

> **`should` is advisory and never fails verification.** […] the
> unchecked-`should` count is surfaced — as visibility, not as an error.
>
> — [addendum §3.1](../spec/ABSICHT-MODEL-ADDENDUM.md#31-outcome-carries-polarity-timing-carries-when)

## What to build

In `absicht.verify`:

- **Evidence discovery** — how "something checks it" is established. Follow
  whatever mechanism 40/41 built for `done_when` criteria (step
  definitions, contract tests, assertions); observations join that
  mechanism, they do not get a new one. The observation id
  (`behavior:x#obs-2`) is the anchor evidence points at, exactly as
  criterion ids anchor step definitions — that stability-across-rewording
  is why anchored ids exist. If 40/41's mechanism turns out to be
  file-reference based, an observation is `checked` when an evidence ref
  names its id and that ref exists; the *quality* of the evidence is out of
  scope (absicht does not run checks).
- **Per-observation results** over the packet's `satisfy` and
  `must_not_break` behaviors: `must` / `must_not` → `checked` or
  `no_check`; `should` → always `advisory`, with checked-ness noted inside
  the advisory detail.
- **Reporting**, through `absicht.findings` like every verify rule:
  `no_check` on a `must`/`must_not` in the **satisfy** set is an error
  finding; on the **must-not-break** set, a warning (new work must guard
  its expectations; pre-existing unguarded expectations are drift to
  surface, not a gate to fail this slice on — and `--strict` exists).
  Advisory results and the unchecked-`should` count go in the report
  summary, never into the exit-code decision.
- **Run store**: the full per-observation result set recorded via
  `absicht.runstore.record_run` — `(packet id, commit sha, per-criterion
  result, evidence ref)`, one row per observation and per `done_when`
  criterion. Also finish [58](58-run-store.md)'s wiring if `ab verify`
  landed after it.
- Rule registration + `--explain` text for the new rule ids (follow 41's
  naming for verify rules).

## Out of scope

- Running any test, probe, metric query, or assertion. Evidence is
  referenced, never executed.
- An evidence-hint field on observations — open question §10.3; do not
  pre-decide it by inventing a convention here beyond what 40/41 already
  built.
- Timing enforcement — effective timing is *reported* with each result
  (from 51's helper); whether the evidence actually waits for eventual
  consistency is the evidence's business.

## Tests

- A packet whose satisfy-behavior has three observations: evidence for one
  → one `checked`, two `no_check` errors naming the observation ids.
- `must_not` observations get the same treatment as `must` (the addendum's
  double-write example: absence-of-entry needs a check too).
- `should` never alters the exit code, appears as `advisory`, and the
  unchecked-`should` count lands in text and `--json` summaries.
- must-not-break `no_check` is warn (exit 0), error under `--strict`.
- After a run, `runstore.runs_for(packet_id)` returns every observation row
  with result and evidence ref.

## Definition of done

- `./scripts/verify.sh` clean.
