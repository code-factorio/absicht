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
- name: observation
  type: str
- name: result
  type: checked|no_check|advisory
- name: evidence-ref
  type: str
identity:
- packet-id
- observation
---

One row per observation per run. Re-derivable by re-running, expensive to
lose.
