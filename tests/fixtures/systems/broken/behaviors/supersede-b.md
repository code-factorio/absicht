---
id: behavior:supersede-b
title: Replaced by supersede-a
state: specified
confidence: reviewed
owner: dana
supersedes:
- behavior:supersede-a
trigger: Something happens.
observations:
- id: behavior:supersede-b#obs-1
  statement: A row lands in the store.
  at: resource:audit-store
  outcome: must
---
The other half of the supersession cycle.
