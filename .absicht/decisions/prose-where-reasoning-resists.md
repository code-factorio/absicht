---
id: decision:prose-where-reasoning-resists
title: Structured records, prose only where reasoning resists fields
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: An ADR whose context is `["performance", "vendor_lock_in"]` has thrown
  away the argument, and the argument is the non-derivable half this project
  exists to hold; but fields are what compute, because queries, checks and
  packets walk them and not prose.
choice: The model is structured records, and prose survives only where the
  reasoning resists fields.
consequences:
- Components, interfaces, data entities, milestones and behaviors are pure
  structure.
- ADR context, quality-requirement rationale and rejections keep a prose body,
  in the file so it
  diffs, reviews and merges like text.
- A field exists only if something computes over it; everything else is body.
alternatives:
- An ADR whose context is a list of tags, which throws the argument away.
- Fields for everything, which nothing can walk when the fact is an argument.
applies_to:
- component:models
decided_on: 2026-08-15
---

## Context

An ADR whose context is `["performance", "vendor_lock_in"]` has thrown away
the argument — and the argument is the non-derivable half this project
exists to hold. But fields are what compute: queries, checks and packets
walk them, not prose.

## Consequences

Components, interfaces, data entities, milestones and behaviors are pure
structure. ADR context, quality-requirement rationale and rejections keep a
prose body, in the file so
it diffs, reviews and merges like text. A field exists only if something
computes over it; everything else is body.
