# 25 — `ab layout`

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md).

## Spec
> Positions are design data, not a rendering detail. Stable layout is what
> makes the diagrams worth having — if boxes move on every build, spatial
> memory never forms.
>
> - `--recompute` re-run the deterministic layout for new elements only
> - `--recompute-all` throw away pinned positions
> - `--seed N`
> - `--check` fail if any element has no position
>
> — [`../spec/cli.md`](../spec/cli.md#ab-layout)

This is the one command in step 2 with a genuinely open design question:
*what layout algorithm.* Don't over-invest — this project explicitly isn't
building a canvas/diagramming suite (README's "Not this" section), the bar
is "stable and legible enough for a generated diagram," not aesthetically
optimal graph drawing.

## What to build

A `Layout` model (add to `models.py` if it doesn't exist by the time this
lands — check first; [`00-conventions.md`](00-conventions.md)'s file-layout
table names `layout.yaml` as a singleton but the current `models.py` has no
`Layout`/`Position` type yet) holding, at minimum, `positions: dict[Ref,
tuple[float, float]]` or an equivalent `tuple[Position, ...]` of `(ref, x,
y)` — pydantic-friendly, matching this project's preference for tuples over
dicts where order/hashability matters (dict is probably fine here since
position lookup by ref is the access pattern, not iteration order — but stay
consistent with how the rest of `models.py` makes this choice per field).

`src/absicht/layout.py`:

- A **deterministic** layout function: same graph + same `--seed`, same
  positions, every time — this is the property the whole command exists to
  guarantee (`verification.md` names SVG-under-pinned-layout as its own CI
  job for exactly this reason). A force-directed layout seeded from
  `--seed` (e.g. via `networkx.spring_layout` if a graph library is worth
  adding as a dependency, or a hand-rolled simple deterministic layered
  layout — components at one rank, seams at another — given the graphs here
  are small and mostly hierarchical via `contains`) both satisfy this;
  picking a graph-library dependency is a real call, make it and say why in
  the commit, don't leave it implicit.
- `--recompute`: positions for elements *without* an existing pinned
  position get computed and added; existing positions in `layout.yaml`
  are untouched (this is what "stable layout" means in practice — a new
  component shouldn't reshuffle the whole diagram).
- `--recompute-all`: discard everything, lay out from scratch.
- `--check`: `FINDINGS` if any element from the current `Design` (all kinds
  that participate in diagrams — likely `components`, `seams`,
  `externals`, and whatever [`27-render-diagrams.md`](27-render-diagrams.md)
  ends up drawing; confirm against that task once it exists, or make a
  reasonable call now and let 27 push back if it's wrong) has no entry in
  `layout.yaml`.
- Writes `layout.yaml` via `absicht.codec.dump_singleton`.

## Out of scope

- No interactive drag-to-reposition — README's own status table marks that
  "later," possibly never (*"No editor before step 4, and possibly never
  beyond dragging boxes"*).
- No per-overlay layout variation — `--overlay` in `ab render`
  ([`27-render-diagrams.md`](27-render-diagrams.md)) is explicitly *"same
  layout, different colouring,"* so this command produces exactly one set of
  positions, not one per overlay.

## Tests

- Two runs with the same `--seed` over the same `Design` produce identical
  `layout.yaml` content.
- `--recompute` on a `layout.yaml` that already covers most elements only
  adds positions for the new ones, leaves the rest byte-identical.
- `--recompute-all` changes everything (or at least doesn't require the old
  values to survive — the test is "recomputes," not "produces different
  values," since a deterministic algorithm with the same seed and same
  graph could legitimately reproduce the same numbers).
- `--check` against a `layout.yaml` missing one element's position:
  `FINDINGS`, names the element.

## Definition of done

- `absicht.layout` added to the import-linter layers list.
- `tests/test_cli.py`: `layout` removed from the "not implemented"
  parametrization.
- If a new dependency (e.g. `networkx`) was added, declared in
  `[project.dependencies]` and `uv lock` run.
- `./scripts/verify.sh` clean.
