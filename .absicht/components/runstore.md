---
id: component:runstore
title: runstore
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: The SQLite run history beside the design store — packet
  issuances and verification runs. Appended per run, never committed, losing
  it loses history not design.
parent: component:ab
implemented_by:
- absicht#src/absicht/runstore.py
relates:
- to: req:bounded-handoff
  type: implements
- to: req:verify-returned-work
  type: implements
- to: resource:runs-db
  type: depends_on
---
