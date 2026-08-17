---
id: decision:renderers-last
title: Renderers land last, not first
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-16
reversibility: cheap
applies_to:
- component:render
- component:diagram
---

## Context

The additions surfaced during UI design work, which is where they were
noticed, not where they live. Roughly 95% of reads are machine reads.

## Consequences

Every model change lands in schema, check, packet, verify and the CLI before
the site touches it. A design that is only reachable through the browser is
a defect — if an addition cannot be authored and read from the CLI, it is
wrong.
