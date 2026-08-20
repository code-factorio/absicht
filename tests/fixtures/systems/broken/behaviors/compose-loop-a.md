---
id: behavior:compose-loop-a
title: Composes compose-loop-b
state: specified
confidence: reviewed
owner: dana
trigger: Something happens.
observations:
- id: behavior:compose-loop-a#obs-1
  statement: The other behavior occurs.
  at: behavior:compose-loop-b
  outcome: must
---
The composition half of the cycle family: each behavior asserts that the other
occurs.
