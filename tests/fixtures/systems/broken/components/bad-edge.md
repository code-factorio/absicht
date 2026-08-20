---
id: component:bad-edge
title: Calls a library
state: specified
confidence: reviewed
owner: dana
level: container
parent: component:root
relates:
- to: resource:audit-store
  type: calls
---
`integrity/edge-kinds`: a `calls` edge ends at an interface, an external
service or a design — never at a resource.
