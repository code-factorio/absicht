---
id: behavior:packet-bounds-the-work
title: A packet bounds the work
state: specified
lifecycle: active
owner: vfeenstr
trigger: A packet is assembled for a milestone with scope.
observations:
- id: behavior:packet-bounds-the-work#obs-1
  statement: Scope elements ride at full fidelity and one ring of neighbours
    at contract fidelity
  at: component:packet
  outcome: must
  timing: immediate
- id: behavior:packet-bounds-the-work#obs-2
  statement: The issuance is appended to the run store with the target agent
  at: resource:runs-db
  outcome: must
  timing: immediate
- id: behavior:packet-bounds-the-work#obs-3
  statement: Note content rides in the packet
  at: component:packet
  outcome: must_not
- id: behavior:packet-bounds-the-work#obs-4
  statement: A human can read the markdown rendering without the model
  at: component:packet
  outcome: should
- id: behavior:packet-bounds-the-work#obs-5
  statement: Behavioural observations arrive as generated .feature files
  at: component:gherkin
  outcome: must
  timing: immediate
- id: behavior:packet-bounds-the-work#obs-6
  statement: The agent works from the sealed packet without the design store
  at: component:packet
  outcome: must
  timing: immediate
relates:
- to: req:bounded-handoff
  type: realizes
---
