# 56 — Derived scope, composition, and `superseded_by`

## Depends on
[00-conventions.md](00-conventions.md),
[50-addendum-conventions.md](50-addendum-conventions.md),
[52-store-wiring.md](52-store-wiring.md).

## Goal

The three computed facts the addendum insists are never stored: a behavior's
scope classification, the composition graph, and the supersession reverse
edge. One home for each computation, in the resolve/index layer, so `list`,
`show`, `packet` and `verify` all read the same answer instead of four
reimplementations.

## Spec

> The set of elements a behavior touches is the union of its observations'
> `at` refs. Classification follows: **local** — one component, no
> resources, no seams; **system** — anything else. Nothing is stored and the
> author never picks a level. […] Same discipline as `ready` and epic status
> in Rohrpost: state the primitive, compute the structure.
>
> — [addendum §4.1](../spec/ABSICHT-MODEL-ADDENDUM.md#41-scope-is-computed-never-declared)

> An observation may assert that another behavior occurs. […] **The packet
> scope walk stops at one hop.**
>
> — [addendum §4.2](../spec/ABSICHT-MODEL-ADDENDUM.md#42-composition)

> `superseded_by` is **derived**, never stored on both sides.
>
> — [addendum §5](../spec/ABSICHT-MODEL-ADDENDUM.md#5-lifecycle-and-supersession)

## What to build

In `absicht.resolve` (extending `Index`, or a sibling structure if `Index`
is getting crowded — the layer is what matters, not the class):

- `touches(behavior) -> tuple[Ref, ...]` — the union of the behavior's
  observations' `at` refs, deduplicated, id-ordered (determinism).
  Composition targets (`behavior:` refs) are *not* scope — a composed
  behavior's own touches stay its own; §4.1's classification reads the
  direct observations only. Pin that reading in the docstring: it is the
  one-hop discipline applied to scope.
- `scope_of(behavior) -> Scope` — `Scope` a two-valued `StrEnum`
  (`local` / `system`) in `models.py`: local iff the non-behavior touches
  are exactly one component ref and nothing else; system otherwise
  (including zero touches — nothing observed anywhere is not "local", and
  the policy rule already flags it).
- `composes(behavior) -> tuple[Ref, ...]` / `composed_by(behavior)` — the
  behavior-to-behavior edges, both directions, from observations' `at`.
- `superseded_by(ref) -> tuple[Ref, ...]` — reverse of stored `supersedes`.
  If `Index`'s generic reverse-reference machinery already answers this,
  wrap it with the name rather than re-indexing; the call sites read
  "superseded_by", not "referrers filtered by field".
- Surfacing (the CLI slice deliberately lives here, not in 55, so the
  computation and its exposure land together):
  - `ab show behavior:x` gains `scope`, `composes`, `composed_by`,
    `superseded_by` — text and `--json` (additive fields).
  - `ab list behavior` gains the scope column and `--scope {local,system}`
    filter.
  - A superseded behavior renders visibly marked wherever it appears.

## Out of scope

- The packet's one-hop expansion and must-not-break list —
  [57](57-packet-behaviors.md) consumes `touches`/`composes` from here.
- Cycle *findings* — [54](54-check-addendum-rules.md); this task's walks
  may assume `check` passed but must not hang on a cyclic fixture (walks
  over possibly-broken input guard with the same visited-set discipline
  `trace` uses).

## Tests

- Scope: one component → local; component + resource → system; two
  components → system; composition-only observations → system; adding a
  second component's observation flips local → system with no other edit
  (the addendum's own motivating sentence).
- `superseded_by` appears on the superseded side without any stored field
  (assert the file contains no such key); chains of two supersessions
  answer one hop each, not transitively.
- `composed_by` is the exact inverse of `composes` over the clean fixture.
- Determinism: all derived tuples id-ordered.

## Definition of done

- `./scripts/verify.sh` clean.
