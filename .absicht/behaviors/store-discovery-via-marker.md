---
id: behavior:store-discovery-via-marker
title: Store discovery via marker
state: specified
lifecycle: active
owner: vfeenstr
trigger: An implementing repo carries an .absicht marker.
realizes:
- requirement:track-implementation
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
  statement: A resource appears as a seam party
  at: component:markers
  outcome: must_not
---
