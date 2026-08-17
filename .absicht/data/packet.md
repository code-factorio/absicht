---
id: data:packet
title: Packet
state: specified
confidence: verified
owner: vfeenstr
owner_component: component:packet
fields:
- name: milestone
  type: Ref
- name: design-rev
  type: str
- name: satisfy
  type: tuple[Ref, ...]
  note: behaviors this slice must newly satisfy
- name: must-not-break
  type: tuple[Ref, ...]
  note: active behaviors touching scope
- name: scenarios-digest
  type: str
identity:
- milestone
- design-rev
---

Deterministic from milestone plus design rev — regenerated rather than
stored. The lock sidecar carries both ends of the seal.
