---
id: component:status
title: status
state: specified
confidence: verified
owner: vfeenstr
responsibility: The read-only drift report joining the design store with the
  repos' markers — which units are behind, which decisions landed, which
  consumers have not caught up.
consumes:
- seam:design-artifact
implemented_by:
- absicht#src/absicht/status.py
---
