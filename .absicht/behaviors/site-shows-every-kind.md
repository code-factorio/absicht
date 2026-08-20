---
id: behavior:site-shows-every-kind
title: The site shows every kind
state: specified
lifecycle: active
confidence: reviewed
owner: vfeenstr
trigger: The site is generated from the store.
observations:
- id: behavior:site-shows-every-kind#obs-1
  statement: Every element kind has pages
  at: component:render
  outcome: must
  timing: immediate
- id: behavior:site-shows-every-kind#obs-2
  statement: The note inbox is one of them
  at: component:render
  outcome: must
  timing: immediate
relates:
- to: req:render-site
  type: realizes
---
