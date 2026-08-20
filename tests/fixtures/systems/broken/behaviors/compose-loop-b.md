---
id: behavior:compose-loop-b
title: Composes compose-loop-a
state: specified
confidence: reviewed
owner: dana
trigger: Something happens.
observations:
- id: behavior:compose-loop-b#obs-1
  statement: The other behavior occurs.
  at: behavior:compose-loop-a
  outcome: must
---
The other half of the composition loop.
