---
id: behavior:supersede-b
title: Supersession cycle, second side
state: specified
trigger: A file exercises the other side of a supersession cycle.
supersedes:
- behavior:supersede-a
observations:
- id: behavior:supersede-b#obs-1
  statement: The second side of the cycle is observable
  at: component:dangling
  outcome: must
---
