---
id: data:design
title: Design artifact
state: specified
confidence: verified
owner: vfeenstr
owner_component: component:build
fields:
- name: schema-version
  type: int
- name: system
  type: System
- name: requirements
  type: tuple[Requirement, ...]
- name: components
  type: tuple[Component, ...]
- name: seams
  type: tuple[Seam, ...]
- name: behaviors
  type: tuple[Behavior, ...]
- name: decisions
  type: tuple[Decision, ...]
- name: milestones
  type: tuple[Milestone, ...]
---

Field names carry dashes where the model spells underscores — the store's
Slug pattern forbids underscores, a constraint ab's own data shapes hit.

Every collection a tuple in id order, the dump's field order the model's own:
byte-identical output needs that order to be data, not dict insertion order.
