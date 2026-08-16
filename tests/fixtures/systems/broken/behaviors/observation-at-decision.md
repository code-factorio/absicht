---
id: behavior:observation-at-decision
title: Observation pointing at a decision
state: specified
trigger: A file exercises an observation whose at is the wrong kind.
observations:
- id: behavior:observation-at-decision#obs-1
  statement: The observation points at a decision, which no observation may do
  at: decision:one-way-no-why
  outcome: must
---
