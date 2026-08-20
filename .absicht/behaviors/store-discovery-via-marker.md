---
id: behavior:store-discovery-via-marker
title: Store discovery via marker
state: specified
lifecycle: active
owner: vfeenstr
trigger: An implementing repo carries an .absicht marker.
observations:
- id: behavior:store-discovery-via-marker#obs-1
  statement: A marker disagreeing with the store fails marker check — the
    store wins
  at: component:markers
  outcome: must
  timing: immediate
- id: behavior:store-discovery-via-marker#obs-2
  statement: Stamping writes the watermark into the repo from the commit that
    lands the work
  at: resource:git-repository
  outcome: must
  timing: immediate
- id: behavior:store-discovery-via-marker#obs-3
  statement: A resource appears as an interface party
  at: component:markers
  outcome: must_not
- id: behavior:store-discovery-via-marker#obs-4
  statement: A watermark behind design head exits FINDINGS under
    --fail-on-drift, naming the unit and the gap
  at: component:status
  outcome: must
  timing: immediate
relates:
- to: req:track-implementation
  type: realizes
---
