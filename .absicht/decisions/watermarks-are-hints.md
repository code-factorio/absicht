---
id: decision:watermarks-are-hints
title: Watermarks are hints, not pins
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: cheap
context: Watermarks over-claim in practice — a merge stamps `M003` because the
  work was declared done, not because it was finished — so the gap always reads
  smaller than it is.
choice: A watermark is a hint about where the code stands, never a pin, and never
  the only route from design to code.
consequences:
- 'It self-corrects on touch: the next packet against a component compares design
  to reality and the lie dies.'
- What `ab status` computes is a fact about two commits, which is true
  regardless.
alternatives:
- Treating the watermark as a pin, which makes the gap read smaller than it is.
applies_to:
- component:status
- component:markers
decided_on: 2026-08-15
---

## Context

Watermarks over-claim in practice — a merge stamps `M003` because the work
was declared done, not because it was finished — so the gap always reads
smaller than it is.

## Consequences

The watermark is never the only route to code, and it self-corrects on
touch: the next packet against a component compares design to reality and
the lie dies. What `ab status` computes is a fact about two commits, which
is true regardless.
