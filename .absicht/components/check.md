---
id: component:check
title: check
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: The validator's three layers — schema, integrity, policy —
  each a flat list of findings, including the addendum rules for resources,
  behaviors, observations and notes.
parent: component:ab
implemented_by:
- absicht#src/absicht/check.py
relates:
- to: req:validate-store
  type: implements
- to: interface:findings-report
  type: calls
---
