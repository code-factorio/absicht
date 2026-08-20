---
id: behavior:scope-is-derived
title: Scope is derived
state: specified
lifecycle: active
owner: vfeenstr
trigger: A behavior's observations change.
observations:
- id: behavior:scope-is-derived#obs-1
  statement: The local-or-system classification recomputes with no stored
    field and no author choice
  at: component:resolve
  outcome: must
  timing: immediate
- id: behavior:scope-is-derived#obs-2
  statement: A second component appearing in at promotes a local behavior to
    system with no edit to say so
  at: component:resolve
  outcome: must
  timing: immediate
- id: behavior:scope-is-derived#obs-3
  statement: A derived value is written back into a store file
  at: resource:store-tree
  outcome: must_not
relates:
- to: req:model-elements
  type: realizes
---
