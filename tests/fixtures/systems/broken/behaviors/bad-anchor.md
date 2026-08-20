---
id: behavior:bad-anchor
title: An observation belonging to another behavior
state: specified
confidence: reviewed
owner: dana
trigger: Something happens.
observations:
- id: behavior:somewhere-else#obs-1
  statement: A row is written.
  at: component:root
  outcome: must
---
`store/validation`: the id says which behavior owns an observation, so one
naming another behavior is a broken file rather than a design judgement.
`Behavior`'s own validator refuses it at parse time.
