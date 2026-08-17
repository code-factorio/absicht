---
id: behavior:diagrams-keep-their-positions
title: Diagrams keep their positions
state: specified
lifecycle: active
owner: vfeenstr
trigger: The site is regenerated against a pinned layout.
realizes:
- requirement:render-site
observations:
- id: behavior:diagrams-keep-their-positions#obs-1
  statement: The same element sits at the same coordinates as the previous run
  at: component:layout
  outcome: must
  timing: immediate
- id: behavior:diagrams-keep-their-positions#obs-2
  statement: The SVG bytes are identical across regenerations
  at: component:diagram
  outcome: must
  timing: immediate
- id: behavior:diagrams-keep-their-positions#obs-3
  statement: Render invents its own positions when layout.yaml is silent
  at: component:render
  outcome: must_not
---
