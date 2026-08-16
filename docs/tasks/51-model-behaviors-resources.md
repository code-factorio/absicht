# 51 — Model: Resource, Behavior, Observation, Note

## Depends on
[00-conventions.md](00-conventions.md),
[50-addendum-conventions.md](50-addendum-conventions.md).

## Goal

The foundation of the whole 5x block: the four new types in
`src/absicht/models.py`, and the regenerated JSON Schema. Nothing else in the
addendum can start until the model can say it. This task is models and schema
only — no loading, no CLI, no rules that need a second element to check.

## Spec

> An addressable thing the system depends on but does not design. […]
> `technology` is free text, forever. […] `kind` is three values, and it is
> read. […] There is no `provided_by`.
>
> — [addendum §1](../spec/ABSICHT-MODEL-ADDENDUM.md#1-resource)

> An expectation about how the system acts. […] `trigger` is prose — a
> sentence naming what happened. […] Behaviors carry `state` like any
> element. […] behaviors carry a second axis: `lifecycle: active | superseded`
> with supersession recorded on the replacement. `superseded_by` is
> **derived**, never stored on both sides.
>
> — [addendum §2, §5](../spec/ABSICHT-MODEL-ADDENDUM.md#2-behavior)

> Anchored to its behavior, following the existing pattern for criteria. […]
> `outcome` carries polarity, `timing` carries when. […] **`timing` is
> omitted for `must_not`** and its presence is a check error.
>
> — [addendum §3](../spec/ABSICHT-MODEL-ADDENDUM.md#3-observation)

> **Not an element.** […] No kind, no owner, no parent, nothing required
> beyond an id.
>
> — [addendum §6](../spec/ABSICHT-MODEL-ADDENDUM.md#6-note)

## What to build

In `src/absicht/models.py`:

- `ObservationId` — annotated string next to `CriterionId`, pattern
  `^[a-z]+:[a-z0-9][a-z0-9-]*#obs-\d+$`.
- Enums `ResourceKind`, `Outcome`, `Timing`, `Lifecycle` per the table in
  `50-addendum-conventions.md`.
- `Resource(Element)` — `resource_kind: ResourceKind`, `technology: str`
  (free text, required, non-empty). Nothing else: no `provided_by` (§1.3),
  no storage taxonomy (§1.1). Note the naming: `External.external_kind` is
  the precedent for not shadowing a would-be builtin-ish `kind` name.
- `Observation(Record)` — `id: ObservationId`, `statement: str`
  (non-empty), `at: Ref`, `outcome: Outcome = Outcome.MUST`,
  `timing: Timing | None = None`. A model validator rejecting
  `outcome == MUST_NOT and timing is not None` — this makes
  `schema/must-not-has-timing` a parse-time failure, like
  `Criterion._shape_matches_kind`.
- `Behavior(Element)` — `trigger: str` (prose, non-empty),
  `realizes: tuple[Ref, ...] = ()`, `lifecycle: Lifecycle = ACTIVE`,
  `supersedes: tuple[Ref, ...] = ()`,
  `observations: tuple[Observation, ...] = ()`. A validator mirroring
  `Story._criteria_anchored_to_story` for observation anchoring. Do **not**
  validate "no observations is an error" here — a behavior mid-authoring is
  legitimate on disk; that is `policy/behavior-needs-observations`
  ([54](54-check-addendum-rules.md)), a report line, not an exception
  (models.py's own docstring rule 4 / closing paragraph).
- `Note(Record)` — `id: Ref`, `ref: Ref | None = None`, `created: date`,
  `promoted_to: Ref | None = None`, `source: str = ""`, `body: str = ""`.
  Not an `Element` — no title, state, confidence, owner, tags. Not a field
  of `Design`.
- `Design` grows `resources: tuple[Resource, ...] = ()` and
  `behaviors: tuple[Behavior, ...] = ()`.
- Effective-timing helper (a small function or `Observation` method taking
  the resolved target's `ResourceKind | None`) implementing the default
  table from `50-addendum-conventions.md` — it lives here because both
  `packet` and `verify` will need the same answer.

Then `ab schema` regeneration: the committed output in `schema/` must be
refreshed in this task (`ab schema`, commit the diff) — `ab schema --check`
is part of `verify.sh` and a stale schema fails the gate.

## Out of scope

- Loading/writing any of this from disk — [52](52-store-wiring.md) (elements)
  and [53](53-notes.md) (notes).
- Every cross-element rule (dangling `at`, cycles, superseded-in-milestone) —
  [54](54-check-addendum-rules.md).
- Derived scope, `superseded_by`, composition — [56](56-derived-scope-composition.md).

## Tests

- `Resource` rejects a missing/empty `technology`; accepts any string in it.
- `Observation` with `outcome: must_not` and any `timing` fails validation;
  `must`/`should` accept `timing` absent or present.
- `Behavior` rejects an observation anchored to a different behavior id;
  accepts zero observations.
- Effective timing: authored value wins; `store`/`endpoint` default
  `immediate`; `stream` defaults `eventual`; non-resource target defaults
  `immediate`.
- `Note` requires only `id` and `created`; `Design` round-trips with
  resources and behaviors present and absent (schema_version untouched —
  additive fields, no bump; see `00-conventions.md` on additive JSON).

## Definition of done

- `schema/` regenerated and committed; `ab schema --check` passes.
- `./scripts/verify.sh` clean.
