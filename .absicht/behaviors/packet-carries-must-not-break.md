---
id: behavior:packet-carries-must-not-break
title: A packet carries what must not break
state: specified
lifecycle: active
owner: vfeenstr
trigger: A packet is assembled while standing behaviors touch its scope.
realizes:
- requirement:bounded-handoff
observations:
- id: behavior:packet-carries-must-not-break#obs-1
  statement: Active behaviors touching scope are listed under must-not-break
  at: component:packet
  outcome: must
  timing: immediate
- id: behavior:packet-carries-must-not-break#obs-2
  statement: A superseded behavior appears in the must-satisfy list
  at: component:packet
  outcome: must_not
- id: behavior:packet-carries-must-not-break#obs-3
  statement: Composition expands one hop and references the rest without
    expanding it
  at: component:packet
  outcome: must
  timing: immediate
---
