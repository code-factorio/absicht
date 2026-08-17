---
id: behavior:diff-speaks-in-elements
title: Diff speaks in elements
state: specified
lifecycle: active
owner: vfeenstr
trigger: The design is compared across two revisions.
realizes:
- requirement:track-implementation
observations:
- id: behavior:diff-speaks-in-elements#obs-1
  statement: Added decisions, moved seams and state transitions list as
    elements
  at: component:diff
  outcome: must
  timing: immediate
- id: behavior:diff-speaks-in-elements#obs-2
  statement: A store file is written for either side of the comparison
  at: resource:store-tree
  outcome: must_not
---
