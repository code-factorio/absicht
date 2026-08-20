---
id: decision:resource-kind-three-values
title: A resource kind is three values, and it is read
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: A `kind` earns its place only if something in absicht branches on it,
  and the axis that qualifies is what an observation about the resource looks
  like and therefore how it is checked.
choice: A resource kind is a closed set of three values — `store`, `endpoint` and
  `stream` — each implying a default observation timing.
consequences:
- Anything merely descriptive goes in `technology`, which is free text forever,
  or in a tag.
- A fourth value is a spec change, not an edit.
alternatives:
- Every storage taxonomy, which is a schema change waiting to happen; see
  `rejection:storage-taxonomy`.
applies_to:
- component:models
decided_on: 2026-08-16
---

## Context

A `kind` earns its place only if something in absicht branches on it. The
axis that qualifies is what an observation about the resource looks like and
therefore how it is checked. Every storage taxonomy is a schema change
waiting to happen — see `rejection:storage-taxonomy`.

## Consequences

`store`, `endpoint`, `stream`, each implying a default observation timing.
Anything merely descriptive goes in `technology` (free text, forever) or a
tag. A fourth value is a spec change, not an edit.
