# 24 — `ab trace REF`

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md),
[20-build.md](20-build.md).

## Spec
> Traceability paths through the graph: requirement to component to seam to
> decision, in either direction.
>
> - `--to REF` paths between two elements
> - `--up` / `--down` direction. Default both
> - `--format {text,json,mermaid}`
>
> — [`../spec/cli.md`](../spec/cli.md#ab-trace-ref)

## What to build

Replace `unimplemented(ctx)` in `trace()`, `src/absicht/cli/query.py`:

- Without `--to`: every reachable path from `REF` outward (`--down`, e.g.
  requirement → realizing component → seam it provides → decisions that
  `applies_to` it) and/or inward (`--up`, the reverse), bounded to something
  sane — an unbounded search on a real graph needs a depth cap or cycle
  guard even though [`13-check-integrity.md`](13-check-integrity.md) should
  mean cycles don't exist in a *clean* store; don't assume clean, this
  command should not hang on a `broken/`-shaped input, it should terminate
  and probably surface that a cycle was hit rather than looping.
- With `--to REF2`: paths *between* `REF` and `REF2` specifically — BFS/DFS
  restricted to routes that reach `REF2`, not the full reachable set. This
  is the harder, more useful half of the spec line ("paths between two
  elements") — don't build only the "everything reachable" case and call
  `--to` a filter over it if the graph is large enough that this matters;
  for this project's scale it may genuinely be fine to compute reachable
  paths and filter, but say which approach you took and why, since the
  spec's phrasing implies point-to-point pathfinding was the intended
  feature.
- `--up`/`--down` both false (neither given): both directions, per spec
  default. Both given: also both directions (not an error — `--up --down`
  together is redundant, not contradictory).
- `--format text`, `json` (list of paths, each a sequence of refs +
  relation names), `mermaid` (a `graph TD` or `flowchart` block — this is
  the format [`27-render-diagrams.md`](27-render-diagrams.md) also needs for
  its `--format mermaid` diagrams; factor the ref-graph→mermaid renderer so
  both call the same function instead of two mermaid emitters drifting
  apart).

## Out of scope

- No layout/positioning concerns — that's `ab layout`
  ([`25-layout.md`](25-layout.md)); `trace`'s mermaid output can let mermaid
  auto-layout itself, it doesn't need pinned coordinates the way SVG
  rendering does.

## Tests

- Against `clean/`: a known requirement→component→seam→decision chain comes
  back as an expected path.
- `--to` between two elements with a real path, and between two with none
  (empty result, `OK` — no path found is not an error, it's information).
- `--up`/`--down` each independently restrict direction on a fixture chosen
  to have asymmetric structure.
- A cycle (from `broken/`) doesn't hang the command — bound this with a
  test that has a timeout or an explicit assertion on the guard, not just
  "it happened to finish."

## Definition of done

- `tests/test_cli.py`: `trace` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
