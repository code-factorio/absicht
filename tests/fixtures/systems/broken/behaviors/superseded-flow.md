---
id: behavior:superseded-flow
title: The flow a later slice replaced
state: specified
lifecycle: superseded
trigger: A customer places an order the old way.
observations:
- id: behavior:superseded-flow#obs-1
  statement: The order lands in the audit store
  at: resource:audit-store
  outcome: must
---
