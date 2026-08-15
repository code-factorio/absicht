# 27 — `ab render`: diagrams

## Depends on
[25-layout.md](25-layout.md), [26-render-site.md](26-render-site.md) (this
task completes the same command; land it after 26 exists so the diagrams
have a site to embed into, even though the diagram-generation logic itself
doesn't technically require 26's HTML pages).

## Spec
> - `--overlay {state,milestone,coverage,churn}` repeatable; same layout,
>   different colouring
> - `--format {svg,mermaid,d2}` diagram output
>
> — [`../spec/cli.md`](../spec/cli.md#ab-render)

## What to build

Add to `src/absicht/render.py` (or a `absicht/diagram.py` submodule if the
site-generation and diagram-generation code don't share enough to justify
one file — your call once you see how much they actually share, likely just
the resolved `Design`+`Layout` inputs):

- A diagram is components/seams/externals (the same node set
  [`25-layout.md`](25-layout.md) positions) as boxes, connected by
  `consumes`/`provides`/`contains` edges, at the pinned coordinates from
  `layout.yaml`. If `ab layout --check` would fail (missing positions), this
  command should say so and point at `ab layout`, not silently fall back to
  an unpinned auto-layout — that would defeat the entire stated purpose of
  pinning positions (*"if boxes move on every build, spatial memory never
  forms"*).
- `--format svg`: hand-emit SVG from the pinned coordinates (boxes,
  labels, edges as lines/arrows) — deterministic by construction, since the
  coordinates already are; this is the format `verification.md`'s
  determinism CI job specifically calls out (*"same for SVG output with a
  pinned layout"*), so keep any non-deterministic detail (float formatting,
  id generation for SVG elements, dict iteration for attributes) out of it —
  format floats with a fixed precision, iterate nodes/edges in a stable
  order.
- `--format mermaid`: reuse [`24-trace.md`](24-trace.md)'s
  ref-graph→mermaid renderer if that's the same shape of output; mermaid
  doesn't take pinned coordinates (it auto-lays-out), so `--overlay`'s
  colouring is the main thing this format needs beyond what `trace` already
  emits.
- `--format d2`: [d2](https://d2lang.com) text output — a boxes-and-edges
  DSL, straightforward to emit by hand (no need for the `d2` CLI/library as
  a dependency; this command only needs to *produce* `.d2` source, not
  render it).
- `--overlay` (repeatable — so multiple overlays can be requested in one
  invocation, presumably as separate output variants, one per overlay,
  since "different colouring" implies one visual result per overlay rather
  than a blend): a colour/style mapping applied at render time —
  `state` (colour by `Element.state`), `milestone` (colour by membership in
  a milestone's `scope` — ambiguous without a specific milestone given
  anywhere in the flag; check whether this needs a companion value or
  colours by "which milestone, if any" per element across all milestones),
  `coverage` (colour by whether an element has a realizing/implementing
  reference — ties into `Component.implemented_by`), `churn` (colour by how
  recently/often an element changed — needs [`05-git.md`](05-git.md)'s
  history, likely commit count or last-touched date over the element's
  `source` path; this is the one overlay that reaches outside the design
  store itself into git, confirm that's intended before assuming).

## Out of scope

- No animation, no interactivity beyond what a generated SVG/mermaid/d2
  file naturally offers when embedded in the site from
  [`26-render-site.md`](26-render-site.md).
- No layout computation — that's `ab layout`; this command only reads
  `layout.yaml`, never writes it.

## Tests

- SVG output is byte-identical across two runs (the determinism property,
  tested here at the unit level — CI's cross-checkout variant is a separate
  job, per `verification.md`).
- Each `--format` produces syntactically plausible output for its DSL (SVG:
  valid XML; mermaid: starts with a recognized diagram-type keyword; d2:
  parses as the expected boxes/edges shape) — a `syrupy` snapshot per
  fixture per format is the natural test, building on
  [`06-fixtures.md`](06-fixtures.md).
- Rendering without `ab layout` having been run first (no `layout.yaml`, or
  one missing positions) fails clearly rather than producing an unpinned
  diagram.
- Each `--overlay` value visibly changes output (e.g. a colour attribute
  differs between two elements known to differ on that overlay's dimension
  in a fixture) — don't just test that the flag is accepted, test that it
  does something.

## Definition of done

- `tests/test_cli.py`: `render` now removed from the "not implemented"
  parametrization (this is the task that completes the command started in
  [`26-render-site.md`](26-render-site.md)).
- `./scripts/verify.sh` clean.
