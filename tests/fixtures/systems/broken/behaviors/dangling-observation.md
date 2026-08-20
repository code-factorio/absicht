---
id: behavior:dangling-observation
title: Watches a ghost
state: specified
confidence: reviewed
owner: dana
trigger: Something happens.
observations:
- id: behavior:dangling-observation#obs-1
  statement: A row lands in the store.
  at: resource:ghost-store
  outcome: must
---
`integrity/dangling-ref`: the generic ref walk covers an observation's `at`,
so the finding lands on the behavior that carries it.
