---
id: behavior:verify-reports-unchecked-observations
title: Verify reports unchecked observations
state: specified
lifecycle: active
owner: vfeenstr
trigger: A change claiming to complete a sealed packet is verified.
observations:
- id: behavior:verify-reports-unchecked-observations#obs-1
  statement: Each must and must_not observation reports checked with evidence
    or no_check
  at: component:verify
  outcome: must
  timing: immediate
- id: behavior:verify-reports-unchecked-observations#obs-2
  statement: An unchecked should is counted as visibility and never failed
  at: component:verify
  outcome: must
  timing: immediate
- id: behavior:verify-reports-unchecked-observations#obs-3
  statement: The run is appended to the run store with the commit sha
  at: resource:runs-db
  outcome: must
  timing: immediate
- id: behavior:verify-reports-unchecked-observations#obs-4
  statement: The verified packet's issuance sits in the same run store,
    beside the run
  at: behavior:packet-bounds-the-work
  outcome: should
  timing: immediate
relates:
- to: req:verify-returned-work
  type: realizes
---
