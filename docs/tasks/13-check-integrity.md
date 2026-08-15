# 13 — `absicht.check`: the integrity layer

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md),
[04-findings.md](04-findings.md), [12-check-schema.md](12-check-schema.md)
(adds to the same module).

## Spec
> integrity (every ref resolves, no cycles in `contains` or `depends_on`,
> criteria anchored to their story)
>
> — [`../spec/cli.md`](../spec/cli.md#ab-check)

Note: criteria anchoring is *already* enforced by `Story._criteria_anchored_
to_story` in `models.py` at parse time — a misanchored criterion never
survives `load` to reach this layer. Confirm this and decide: either this
rule is genuinely unreachable at the integrity layer and the spec line is
satisfied by the schema layer instead (say so in a comment, and register the
rule id as "handled upstream" rather than silently dropping it from
`--explain`'s catalog), or find a shape of misanchoring that *can* slip
through (e.g. a criterion referencing a story id that isn't its own parent
but happens to match the pattern) and write the rule for that. Don't assume
without checking — read the validator in `models.py` first.

## What to build

Add to `src/absicht/check.py`:

- `integrity_findings(design: Design, index: Index) -> tuple[Finding, ...]`:
  - **Dangling refs**: for every ref-typed field (the same list
    [`03-resolve.md`](03-resolve.md) built `Index.referenced_by` from —
    reuse that enumeration rather than hand-copying it a second time; if it
    doesn't already exist as a reusable list/generator in `resolve.py`,
    extracting it there is in scope for *this* task, retroactively, since
    two callers now need it), a target id not present in `Index.by_id` is
    one `Finding` per dangling ref, `rule_id="integrity/dangling-ref"`,
    naming the source element, the field, and the missing target.
  - **Cycles**: `contains` (component nesting — a component containing
    itself, directly or transitively) and `depends_on` (milestone
    dependencies). Standard cycle detection over each relation as its own
    directed graph (DFS with a visiting/visited set, or `graphlib` from the
    standard library — prefer `graphlib.TopologicalSorter`, which raises
    `CycleError` with the cycle already identified, over hand-rolling DFS).
    One `Finding` per distinct cycle found, not per edge in it.
  - **Multi-repo composition sanity** (implied by "every ref resolves" plus
    the README's description of `system.yaml` pinning units like a
    lockfile): an `externals` ref on `System` that doesn't resolve to an
    `External` element, and vice versa if that's a checkable direction —
    decide based on what `System.externals` actually models (it's a tuple of
    `Ref`, so this is just the dangling-ref check applied to that field; it
    may already be covered by the generic dangling-ref sweep above and not
    need its own rule — check before adding a redundant one).

## Out of scope

- Policy judgement (an unresolved question isn't an integrity problem, an
  `unknown` with no owner isn't either) — [`14-check-policy.md`](14-check-policy.md).
- Watermark/marker consistency (`ab check` verifying a repo's `.absicht`
  marker agrees with the store, per the README's Discovery section) — that
  cross-repo concern belongs to [`45-marker-check.md`](45-marker-check.md) /
  `ab marker check`, not the store-internal `ab check`. Re-read the README
  passage if tempted to fold it in here: *"`ab check` verifies the two agree
  and treats a mismatch as an error"* — this could mean either command; if
  after reading both specs it's ambiguous, implement it once, in
  `marker check` (the more specific home), and have `ab check` optionally
  invoke it when repos are known, rather than duplicating the logic.

## Tests

- Against `tests/fixtures/systems/broken/`'s dangling-ref and cycle cases:
  exactly the expected findings, right rule ids, right refs named.
- Against `clean/` and `brownfield/`: zero integrity findings.
- A hand-built two-node cycle and a hand-built three-node cycle in
  `contains` are both caught, and reported as one finding each — not one
  finding per edge.

## Definition of done

- `absicht.check` now imports `absicht.resolve`; confirm the import-linter
  layers list already has `resolve` below `check` (it should, per
  [`00-conventions.md`](00-conventions.md)'s stack) — no change needed there
  unless the stack comment and reality have drifted.
- `./scripts/verify.sh` clean.
