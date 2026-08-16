# 60 — Render: behaviors, resources and the note inbox on the site

## Depends on
[00-conventions.md](00-conventions.md),
[50-addendum-conventions.md](50-addendum-conventions.md),
[53-notes.md](53-notes.md), [56-derived-scope-composition.md](56-derived-scope-composition.md),
[26-render-site.md](26-render-site.md) / [27-render-diagrams.md](27-render-diagrams.md)
— **landed first**; this extends the site, it does not build one.

Deliberately the last addendum task: the addendum's §0 rule is that the
browser is "one projection of the model and the least important consumer of
it". Everything rendered here must already be reachable through the CLI.

## Spec

> | Renderers | static site, served app, diagrams — last, not first |
>
> A design that is only reachable through the browser is a defect.
>
> — [addendum §0](../spec/ABSICHT-MODEL-ADDENDUM.md#0-this-is-a-model-change-not-a-ui-feature)

> Age is surfaced, not just count: "14 notes, oldest 3 months" is useful
> pressure; a bare count is not.
>
> — [addendum §6](../spec/ABSICHT-MODEL-ADDENDUM.md#6-note)

## What to build

In `absicht.render`, following whatever page/partial structure 26 built:

- **Element pages** for resources and behaviors, same template family as
  other kinds. A behavior page shows: trigger, lifecycle (superseded
  visibly struck/badged, linking to its `superseded_by` replacements), the
  derived scope classification, the observation table (statement / at /
  outcome / effective timing — the resolved timing, not the raw field),
  `realizes` links, and composition both ways.
- **Traceability**: requirement pages list realizing behaviors;
  component/resource/seam pages list the behaviors whose observations touch
  them (the site-side reading of `Index` reverse refs — the must-not-break
  question answered visually).
- **Diagrams**: resources appear as distinct node shapes/styles at the
  boundary (they are outside the design boundary — §1 is the argument, the
  diagram should show it); behavior composition renders as its own small
  graph per behavior page or one behaviors overview, whichever 27's
  structure makes cheap. Resources get `layout.yaml` positions like every
  node (`ab layout` should already handle new kinds generically — assert).
- **Note inbox page**: unpromoted notes, oldest first, age headline
  ("N notes, oldest X months"), each note's body rendered, `ref` linked
  when present. Promoted notes visible under their terminal state on an
  archive toggle or section — the record of what became what is part of
  the design story. Notes remain absent from every graph/traceability
  view; the inbox is a list, not nodes.
- **Gaps page**: behaviors/resources join by state, plus the
  zero-observations gap line, mirroring `ab gaps` exactly (the page is a
  projection of the command, not a second implementation).

## Out of scope

- Any authoring/editing affordance — the site stays read-only.
- New overlays beyond what 26 defined; `--overlay coverage` picking up
  observation checked-ness is tempting but belongs with a future decision
  once [59](59-verify-observations.md)'s run store has real data to show.
  Note it as a possibility in the PR description, do not build it.

## Tests

- Golden pages: a behavior page (with composition and a superseded
  predecessor), a resource page, the note inbox — snapshot into the golden
  fixture suite like 26's pages.
- Determinism: two renders byte-identical, including the new diagram nodes
  with pinned layout.
- A superseded behavior's page and its replacement's page cross-link.
- The inbox age headline computed against a fixed `today` (injected, same
  as `check` — no clock reads in render).

## Definition of done

- `./scripts/verify.sh` clean.
