---
id: component:wrong-repo
title: Points into an undeclared repository
state: specified
confidence: reviewed
owner: dana
level: container
parent: component:root
implemented_by:
- ghost#src/nowhere
---
`integrity/repository-unknown`: `design.yaml` declares no repository named
`ghost`, so the link into code resolves to a guess.
