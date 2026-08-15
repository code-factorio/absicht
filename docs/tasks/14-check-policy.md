# 14 — `absicht.check`: the policy layer

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md),
[04-findings.md](04-findings.md), [12-check-schema.md](12-check-schema.md)
(adds to the same module).

## Spec
> policy (an `unknown` needs an owner, a requirement needs a realizing
> component, a `one_way` decision needs a rationale body, an external's
> assumptions have not expired)
>
> — [`../spec/cli.md`](../spec/cli.md#ab-check)

This is the judgement layer, and — per README's state table — the one whose
severities should reflect the project's own stated posture: `unknown`,
`observed`, `delegated` are *legitimate, expected states*, not bugs. Get the
default severities right (see below) or `ab check` will nag brownfield
stores into looking broken, which `verification.md`'s own dogfooding caveat
explicitly warns against.

## What to build

Add to `src/absicht/check.py`:

- `policy_findings(design: Design, index: Index) -> tuple[Finding, ...]`,
  one rule function per bullet, each independently filterable via
  `--rule`/`--exclude-rule` (register each with its own `rule_id`):
  - `policy/unknown-needs-owner` — any element with `state == State.UNKNOWN`
    and `owner is None`. `Severity.ERROR` — the spec's wording ("needs") and
    the README's own posture for `unknown` ("Ask, spike, or mark blocking.
    Never invent") both point at this being a real gap, not advisory.
  - `policy/requirement-needs-realizer` — a `Requirement` with
    `realized_by == ()`. Consider whether this should be suppressed for a
    requirement whose `state` is `unknown`/`delegated` (nothing to realize
    yet, by design) versus one that's `specified` with nothing realizing it
    (a real gap) — read the spec line again: it says "a requirement needs a
    realizing component" unconditionally, so the simplest-first
    implementation is unconditional; if that produces obviously wrong noise
    against `brownfield/` once fixtures exist, that's a signal to add the
    state-based exception, not a reason to add it speculatively now (YAGNI).
  - `policy/one-way-needs-rationale` — a `Decision` with
    `reversibility == Reversibility.ONE_WAY` and an empty (or whitespace-only)
    `body`.
  - `policy/external-assumptions-expired` — an `External` with
    `expires_on` in the past relative to *today* (needs a clock — inject it
    as a parameter, `today: date`, rather than calling `date.today()` inside
    the rule function, so tests are deterministic and `--rev` runs against a
    historical revision could in principle ask "expired as of when" later
    without a rewrite).
  - Consider (read `Question` and `Milestone` again before deciding whether
    to add these — they're implied by "an `unknown` needs an owner" but not
    spelled out as separate spec bullets, so treat them as optional
    extensions, not required for this task): a `Question` past `due_on` with
    no `resolved_by`; a `Milestone.unresolved` question that's already been
    `resolved_by` a decision (stale reference, arguably an integrity concern
    instead — your call, document it either way).
- Default severities per rule, since `--severity` defaults to `warn`
  (`cli.md`'s Global flags... actually `--severity` is `check`-specific, see
  the flag table) — pick `Severity.WARN` for anything that's a legitimate
  incomplete-but-honest state per the README's table, `Severity.ERROR` only
  where the spec's wording ("needs an owner", "needs a rationale") reads as
  a hard requirement rather than a nudge. Write down the reasoning per rule
  in the `--explain` text, since this is the one layer where the severity
  choice is a judgement call worth being able to defend.

## Out of scope

- Multi-repo / watermark policy (`status`'s concerns) — this layer is
  store-internal only.

## Tests

- Against `tests/fixtures/systems/brownfield/`: the expected policy findings
  fire (unowned `unknown`, orphaned elements if that's modeled as a policy
  concern rather than integrity — decide and be consistent with
  [`13-check-integrity.md`](13-check-integrity.md), don't implement
  "orphaned" twice under two different rule ids), and — this is the important
  negative test — nothing about `observed` state alone (with no other
  problem) produces a finding; `observed` being unexplained is the honest
  brownfield default, not a violation.
- Against `clean/`: zero policy findings.
- `policy/external-assumptions-expired` with an injected `today` before and
  after `expires_on`, both directions tested.

## Definition of done

- Every policy rule id registered in the `RuleCatalog` with an `--explain`
  string that states the rule *and* the reasoning for its severity.
- `./scripts/verify.sh` clean.
