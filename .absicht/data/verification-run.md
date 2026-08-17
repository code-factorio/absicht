---
id: data:verification-run
title: Verification run
state: specified
confidence: verified
owner: vfeenstr
owner_component: component:runstore
fields:
- name: packet-id
  type: str
- name: commit-sha
  type: str
- name: criterion
  type: str
- name: result
  type: checked|no_check|advisory
- name: evidence-ref
  type: str
identity:
- packet-id
- criterion
---

One row per criterion per run. Re-derivable by re-running, expensive to lose.
