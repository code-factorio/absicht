# 52 — Store wiring: resources and behaviors through codec, load, resolve, build

## Depends on
[00-conventions.md](00-conventions.md),
[50-addendum-conventions.md](50-addendum-conventions.md),
[51-model-behaviors-resources.md](51-model-behaviors-resources.md).

## Goal

Make the two new element kinds real on disk and in the artifact: a
`resources/` or `behaviors/` file parses through `absicht.codec`, loads
through `absicht.load`, resolves into `Design` through `absicht.resolve`, and
appears in `ab build` output — deterministically, like every other kind. Plus
the fixture updates that give every later 5x task something to run against.

## Spec

> | Surface | What changes |
> |---|---|
> | `model/` | msgspec structs, and therefore the generated JSON Schema |
> | `check` | new validation rules […] |
> | `packet` | behaviors are packet content […] |
>
> — [addendum §0](../spec/ABSICHT-MODEL-ADDENDUM.md#0-this-is-a-model-change-not-a-ui-feature)
> (the `model/`+msgspec cell is stale — see `50-addendum-conventions.md`;
> the row's *point* stands: every surface, CLI before browser)

## What to build

- `absicht.codec`: `resource` and `behavior` in the kind↔directory/model
  mapping (`resources/`, `behaviors/`), front-matter format unchanged.
  Observations serialize inline under `observations:` exactly as criteria do
  under `acceptance:` — if the codec is already generic over pydantic
  models, confirm that with a test rather than adding code.
- `absicht.load`: walk the two new directories into `LoadedStore`; a broken
  behavior file is one finding, not a crash, same as every kind.
- `absicht.resolve`: `Design.resources` / `Design.behaviors` populated;
  `iter_references` must yield `Behavior.realizes`, `Behavior.supersedes`,
  and each `Observation.at` (check `_holds_refs` picks up `Ref` inside
  nested `Observation` records — criteria's `touches` is the precedent),
  so `integrity/dangling-ref` and `Index` reverse lookups cover them for
  free.
- `absicht.build`: nothing new if it is truly generic over `Design`; the
  determinism test extended to a store containing the new kinds proves it.
- Fixtures (`tests/fixtures/systems/`): extend at least `clean` (a resource,
  two behaviors — one composing the other, one superseding an older one —
  with observations exercising `must`/`must_not`/`should` and both timings)
  and `broken` (a seam referencing a resource, an observation `at` a
  decision, a `must_not` with `timing`, a supersession cycle — the trip
  wires [54](54-check-addendum-rules.md) will assert on). `brownfield` gains
  an `observed` behavior (§2: "an import of a brownfield system produces
  `observed` behaviors").

## Out of scope

- `ab new resource|behavior`, `ab note` — [55](55-addendum-query-surface.md),
  [53](53-notes.md).
- Any new check rule bodies — [54](54-check-addendum-rules.md) (though
  `integrity/dangling-ref` firing on a bad `at` may simply start happening
  here via the generic walk; that is welcome, assert it).
- Notes loading — [53](53-notes.md), so notes' exemption from the graph is
  built next to the code that enforces it.

## Tests

- Round-trip: a behavior file with inline observations parses, builds, and
  re-emits byte-identically (`ab build --check` on the extended fixtures).
- `iter_references` yields `realizes`, `supersedes`, and every
  `observation.at` with the behavior as source.
- A dangling `observation.at` in a fixture produces
  `integrity/dangling-ref` naming the behavior, the field, the target.
- Loading the extended `broken` fixture stays a per-file finding, never an
  exception.

## Definition of done

- Extended fixtures committed; golden/determinism suites green against them.
- `./scripts/verify.sh` clean.
