---
id: behavior:timing-follows-the-target
title: Timing follows the target
state: specified
lifecycle: active
owner: vfeenstr
trigger: An observation is authored without a timing.
realizes:
- requirement:model-elements
observations:
- id: behavior:timing-follows-the-target#obs-1
  statement: Pointing at a stream defaults to eventual and everything else to
    immediate
  at: component:models
  outcome: must
  timing: immediate
- id: behavior:timing-follows-the-target#obs-2
  statement: An authored timing survives on a must_not observation
  at: component:models
  outcome: must_not
---
