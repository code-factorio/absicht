---
id: decision:prose-where-reasoning-resists
title: Structured records, prose only where reasoning resists fields
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-15
reversibility: costly
applies_to:
- component:models
---

## Context

An ADR whose context is `["performance", "vendor_lock_in"]` has thrown away
the argument — and the argument is the non-derivable half this project
exists to hold. But fields are what compute: queries, checks and packets
walk them, not prose.

## Consequences

Components, seams, data models, milestones and stories are pure structure.
ADR context, NFR rationale and rejections keep a prose body, in the file so
it diffs, reviews and merges like text. A field exists only if something
computes over it; everything else is body.
