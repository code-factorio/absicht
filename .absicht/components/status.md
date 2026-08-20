---
id: component:status
title: status
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: The read-only drift report joining the design store with the
  repos' markers — which units are behind, which decisions landed, which
  consumers have not caught up.
parent: component:ab
implemented_by:
- absicht#src/absicht/status.py
relates:
- to: req:track-implementation
  type: implements
- to: interface:design-artifact
  type: calls
---
