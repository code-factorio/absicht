---
id: data:audit-log
title: Audit log
state: observed
confidence: assumed
owner: sam
fields:
- name: at
  type: datetime
- name: actor
  type: str
- name: before
  type: json
- name: after
  type: json
---
Nothing in this store points at it: no component claims to own it, and no
observation watches it. That is the orphan `ab list --orphaned` is for.
