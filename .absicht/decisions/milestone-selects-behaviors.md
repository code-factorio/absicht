---
id: decision:milestone-selects-behaviors
title: Milestones select behaviors through includes
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: cheap
context: The addendum says a milestone selects which behaviors a slice must newly
  satisfy, but not where, and a new milestone field would be a second selection
  mechanism beside `includes`.
choice: Behaviors are named in `Milestone.includes` alongside the
  requirements, and no new field is added.
consequences:
- The must-satisfy set is `includes` filtered to `behavior:`.
- Must-not-break is derived from scope minus must-satisfy.
alternatives:
- A new milestone field for behaviors, a second selection mechanism beside
  `includes`.
applies_to:
- component:packet
decided_on: 2026-08-16
---

## Context

The addendum says a milestone selects which behaviors a slice must newly
satisfy, but not where. A new milestone field would be a second selection
mechanism beside `includes`.

## Consequences

Behaviors are named in `Milestone.includes` alongside the
requirements. The must-satisfy set is `includes` filtered to `behavior:`;
must-not-break is derived from scope minus must-satisfy. No new field.
