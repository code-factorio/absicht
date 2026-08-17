---
id: decision:milestone-selects-behaviors
title: Milestones select behaviors through includes
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-16
reversibility: cheap
applies_to:
- component:packet
---

## Context

The addendum says a milestone selects which behaviors a slice must newly
satisfy, but not where. A new milestone field would be a second selection
mechanism beside `includes`.

## Consequences

Behaviors are named in `Milestone.includes` alongside stories and
requirements. The must-satisfy set is `includes` filtered to `behavior:`;
must-not-break is derived from scope minus must-satisfy. No new field.
