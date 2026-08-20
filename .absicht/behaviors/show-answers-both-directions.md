---
id: behavior:show-answers-both-directions
title: Show answers both directions
state: specified
lifecycle: active
confidence: verified
owner: vfeenstr
trigger: The designer asks the design about one element or one path.
observations:
- id: behavior:show-answers-both-directions#obs-1
  statement: List answers with one id per line, pipeable
  at: component:cli
  outcome: must
  timing: immediate
- id: behavior:show-answers-both-directions#obs-2
  statement: Show answers with the derived facts — scope, composition,
    superseded_by
  at: component:render
  outcome: must
  timing: immediate
- id: behavior:show-answers-both-directions#obs-3
  statement: A fact show derives is stored in the element's file
  at: component:render
  outcome: must_not
- id: behavior:show-answers-both-directions#obs-4
  statement: Trace renders paths as element chains in either direction
  at: component:render
  outcome: must
  timing: immediate
relates:
- to: req:query-design
  type: realizes
---
