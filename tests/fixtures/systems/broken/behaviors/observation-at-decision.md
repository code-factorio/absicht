---
id: behavior:observation-at-decision
title: Watches a decision
state: specified
confidence: reviewed
owner: dana
trigger: Something happens.
observations:
- id: behavior:observation-at-decision#obs-1
  statement: The decision is honoured.
  at: decision:one-way-no-why
  outcome: must
---
`integrity/observation-target`: the ref resolves, but a decision cannot be
watched. A component, an interface, a resource or another behavior can.
