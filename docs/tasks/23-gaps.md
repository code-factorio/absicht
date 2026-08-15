# 23 — `ab gaps`

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md),
[20-build.md](20-build.md). Shares filtering vocabulary with
[22-list.md](22-list.md); land after it if convenient so the "state/owner
predicate" helpers can be reused rather than duplicated, though the two
aren't strictly ordered.

## Spec
> Everything unfinished, as a worklist: `unknown`, `observed`, `delegated`,
> open questions, unowned elements, expired external assumptions.
>
> - `--kind KIND` `--owner WHO` `--overdue`
> - `--blocking REF` only gaps that block this element or milestone
> - `--format {text,json}`
>
> — [`../spec/cli.md`](../spec/cli.md#ab-gaps)

## What to build

Replace `unimplemented(ctx)` in `gaps()`, `src/absicht/cli/query.py`:

- A `Gap` shape distinct from a bare `Element` — this command's whole point
  is surfacing *why* something is a gap, so each entry should carry at
  least: the ref, the reason (`state=unknown`, `unowned`,
  `question-overdue`, `external-expired`), and whatever's relevant to that
  reason (owner-needed vs actual due date vs expiry date). Don't just dump
  `--state unknown` elements with no annotation — that's strictly worse
  than `ab list --state unknown`, which already exists.
- Sources of gaps, unioned:
  - Elements with `state in (UNKNOWN, OBSERVED, DELEGATED)`.
  - `Question`s (the whole kind is a gap by construction, per its own
    docstring in `models.py`: *"An `unknown` with an owner and a way out.
    Without those it is a wish."*).
  - Unowned elements — likely a large overlap with the `state=UNKNOWN`
    bucket already, since [`14-check-policy.md`](14-check-policy.md)'s rule
    is specifically about unowned-and-unknown; decide whether "unowned" here
    means "any unowned element regardless of state" (broader) or reuses that
    same predicate, and be deliberate about which — the spec lists them as
    separate bullets, which reads as broader.
  - Expired `External` assumptions — same predicate as
    [`14-check-policy.md`](14-check-policy.md)'s `policy/external-assumptions-expired`;
    reuse that function rather than re-deriving expiry logic a second place.
- `--kind`, `--owner`: filter the unioned set.
- `--overdue`: only `Question`s past `due_on` with no `resolved_by` (the
  only kind of gap with a due date at all — applying `--overdue` when it
  can't mean anything for a non-`Question` gap should just exclude those,
  not error).
- `--blocking REF`: only gaps that `Question.blocks` (or, for a milestone
  ref, gaps referenced by that milestone's `unresolved`) names as blocking
  the given ref, directly or (worth checking against the spec's wording —
  "blocks this element or milestone" doesn't obviously demand transitivity)
  transitively through the dependency graph
  [`03-resolve.md`](03-resolve.md)'s `Index` can walk.

## Out of scope

- No auto-resolution suggestions — this is a worklist, not a planner.

## Tests

- Against `brownfield/`: the expected mix of gap reasons, each correctly
  attributed (an `unknown`-with-no-owner gap should say so, not just appear
  generically).
- `--overdue` against a fixture `Question` with `due_on` in the past and one
  in the future.
- `--blocking REF` against a fixture where a `Question.blocks` names a
  specific milestone.
- Against `clean/`: empty (it's meant to be complete).

## Definition of done

- `tests/test_cli.py`: `gaps` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
