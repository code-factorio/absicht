---
id: component:packet
title: packet
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Selects the bounded brief for a milestone — scope at full
  fidelity, one ring of neighbours at contract fidelity, behaviors to satisfy
  and not break, decisions, freedoms, unknowns, rejections.
parent: component:ab
implemented_by:
- absicht#src/absicht/packet.py
relates:
- to: req:bounded-handoff
  type: implements
- to: interface:design-artifact
  type: calls
- to: interface:run-store
  type: calls
---
