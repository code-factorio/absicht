---
id: behavior:dangling-observation
title: Observation pointing at nothing
state: specified
trigger: A file exercises an observation whose at resolves to no element.
observations:
- id: behavior:dangling-observation#obs-1
  statement: The observation points at a resource the store does not define
  at: resource:ghost-store
  outcome: must
---
