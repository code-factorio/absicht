---
id: behavior:dogfood-store-checks-clean
title: absicht's own store checks clean
state: constrained
lifecycle: active
reversibility: cheap
owner: vfeenstr
trigger: absicht's own design store is checked.
observations:
- id: behavior:dogfood-store-checks-clean#obs-1
  statement: Every element kind has at least one instance
  at: resource:store-tree
  outcome: must
  timing: immediate
- id: behavior:dogfood-store-checks-clean#obs-2
  statement: Check exits zero against absicht's own store
  at: component:check
  outcome: must
  timing: immediate
- id: behavior:dogfood-store-checks-clean#obs-3
  statement: Gaps shows the genuinely open questions as a worklist
  at: component:render
  outcome: must
  timing: immediate
relates:
- to: req:dogfood-in-ci
  type: realizes
---

absicht's own design is the most available honest test of the model: it has
real decisions, real rejections, real open questions and a command surface
that the store must be able to name. CONTEXT.md promised this dogfooding from
the start; this story is it happening.
