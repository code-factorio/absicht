---
id: decision:resource-kind-three-values
title: A resource kind is three values, and it is read
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-16
reversibility: costly
applies_to:
- component:models
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
