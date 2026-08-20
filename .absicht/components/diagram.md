---
id: component:diagram
title: diagram
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Diagram projections — SVG, mermaid, d2 — from the resolved
  Design plus the pinned Layout. Separate from render because the machinery
  is genuinely different from HTML pages.
parent: component:ab
implemented_by:
- absicht#src/absicht/diagram.py
relates:
- to: req:render-site
  type: implements
- to: interface:design-artifact
  type: calls
- to: quality:byte-identical-build
  type: satisfies
---
