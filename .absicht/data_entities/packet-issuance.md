---
id: data:packet-issuance
title: Packet issuance
state: specified
confidence: verified
owner: vfeenstr
owner_component: component:runstore
fields:
- name: milestone
  type: Ref
- name: design-rev
  type: str
- name: packet-id
  type: str
- name: issued-at
  type: timestamp
- name: target-agent
  type: str
identity:
- packet-id
---

One row per ab packet run, written beside the design store, never in git.
