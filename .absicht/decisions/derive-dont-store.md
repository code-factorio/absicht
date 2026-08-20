---
id: decision:derive-dont-store
title: Derive structure, never store it
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: Reverse edges and mirrored aggregates — `superseded_by` on both sides,
  `children[]` beside `parent`, a stored scope level — mean every edit writes
  two files, and two branches adding them conflict on a file neither is
  touching.
choice: The author states the primitive only, and every reverse edge, aggregate
  and scope is computed from it.
consequences:
- Superseded_by, behavior scope, composition and the must-not-break list are
  derived from `supersedes`, `parent` and the observations' `at` refs.
- Derived values appear in `--json` and on the site, and never in a file an
  author edits.
- The codec never writes a derived value.
alternatives:
- Storing the reverse edge beside the primitive, which makes every edit write
  two files.
- A stored scope level, which is the same mirrored aggregate one level up.
applies_to:
- component:resolve
- component:packet
decided_on: 2026-08-16
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
