---
id: behavior:scaffold-minimal-element
title: Scaffolding writes the minimal valid element
state: specified
lifecycle: active
owner: vfeenstr
trigger: A designer scaffolds a new element.
realizes:
- requirement:author-store
observations:
- id: behavior:scaffold-minimal-element#obs-1
  statement: The file exists with the deterministic id from the slug and
    state unknown
  at: component:new
  outcome: must
  timing: immediate
- id: behavior:scaffold-minimal-element#obs-2
  statement: A required field the model has no default for is marked as a
    placeholder the author must replace
  at: component:new
  outcome: must
  timing: immediate
- id: behavior:scaffold-minimal-element#obs-3
  statement: Scaffolding overwrites an existing element
  at: component:new
  outcome: must_not
---
