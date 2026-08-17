---
id: data:marker
title: Discovery marker
state: specified
confidence: verified
owner: vfeenstr
owner_component: component:markers
fields:
- name: design
  type: str
  note: store URL
- name: units
  type: tuple[UnitWatermark, ...]
  note: id, path, at, design_rev per unit
identity:
- design
---

A hint, not a pin: at over-claims because a merge stamps it whether or not
the work was finished.
