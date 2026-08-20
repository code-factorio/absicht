---
id: behavior:bad-timing
title: A must_not that says when
state: specified
confidence: reviewed
owner: dana
trigger: Something happens.
observations:
- id: behavior:bad-timing#obs-1
  statement: No row is written.
  at: component:root
  outcome: must_not
  timing: immediate
---
`store/validation`: `must_not` means at no point, so a timing on it is a shape
the record cannot have. `Observation`'s own validator refuses it at parse time.
