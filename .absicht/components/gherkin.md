---
id: component:gherkin
title: gherkin
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: One direction only — observations in, Gherkin out, never parsed
  back. Deterministic, because the output is generated and agents implement
  step definitions against it.
parent: component:ab
implemented_by:
- absicht#src/absicht/gherkin.py
relates:
- to: req:bounded-handoff
  type: implements
- to: quality:byte-identical-build
  type: satisfies
---
