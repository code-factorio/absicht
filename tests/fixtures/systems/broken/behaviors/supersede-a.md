---
id: behavior:supersede-a
title: Replaced by supersede-b
state: specified
confidence: reviewed
owner: dana
supersedes:
- behavior:supersede-b
trigger: Something happens.
observations:
- id: behavior:supersede-a#obs-1
  statement: A row lands in the store.
  at: resource:audit-store
  outcome: must
---
`integrity/cycle`: each of the pair replaces the other, which leaves
`replaces` undefined.
