---
id: component:layout
title: layout
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Computes and pins diagram positions into layout.yaml.
  Positions are design data, not a rendering detail — stable layout is what
  makes diagrams worth building spatial memory on.
parent: component:ab
implemented_by:
- absicht#src/absicht/layout.py
relates:
- to: req:render-site
  type: implements
---
