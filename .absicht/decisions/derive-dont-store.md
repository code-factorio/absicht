---
id: decision:derive-dont-store
title: Derive structure, never store it
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-16
reversibility: costly
applies_to:
- component:resolve
- component:packet
---

## Context

`superseded_by` on both sides, `children[]` beside `parent`, a stored scope
level: reverse edges and mirrored aggregates mean every edit writes two
files, and two branches adding them conflict on a file neither is touching.
Same discipline as Rohrpost's ready and epic status.

## Consequences

The author states the primitive — `supersedes`, `parent`, the observations'
`at` refs — and the structure is computed: superseded_by, behavior scope,
composition, the must-not-break list. Derived values appear in `--json` and
on the site and never in a file an author edits; the codec never writes
them.
