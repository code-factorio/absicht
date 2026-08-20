---
id: component:render
title: render
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: The element view behind ab show, the gaps worklist, and the
  static site pages — including behavior pages with derived facts and the
  note inbox. Read-only over the resolved design.
parent: component:ab
implemented_by:
- absicht#src/absicht/render.py
relates:
- to: req:query-design
  type: implements
- to: req:render-site
  type: implements
- to: interface:design-artifact
  type: calls
---
