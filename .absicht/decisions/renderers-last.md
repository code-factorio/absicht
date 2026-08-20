---
id: decision:renderers-last
title: Renderers land last, not first
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: cheap
context: The additions surfaced during UI design work, which is where they were
  noticed and not where they live, and roughly 95% of reads are machine reads.
choice: Every model change lands in schema, check, packet, verify and the CLI
  before the site touches it.
consequences:
- A design that is only reachable through the browser is a defect.
- If an addition cannot be authored and read from the CLI, it is wrong.
alternatives:
- Landing a model change where it was noticed, in the site, which serves the 5%
  of reads that are human.
applies_to:
- component:render
- component:diagram
decided_on: 2026-08-16
---

## Context

The additions surfaced during UI design work, which is where they were
noticed, not where they live. Roughly 95% of reads are machine reads.

## Consequences

Every model change lands in schema, check, packet, verify and the CLI before
the site touches it. A design that is only reachable through the browser is
a defect — if an addition cannot be authored and read from the CLI, it is
wrong.
