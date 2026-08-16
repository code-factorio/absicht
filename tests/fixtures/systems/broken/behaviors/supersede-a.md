---
id: behavior:supersede-a
title: Supersession cycle, first side
state: specified
trigger: A file exercises one side of a supersession cycle.
supersedes:
- behavior:supersede-b
observations:
- id: behavior:supersede-a#obs-1
  statement: The first side of the cycle is observable
  at: component:dangling
  outcome: must
---
