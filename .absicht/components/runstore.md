---
id: component:runstore
title: runstore
state: specified
confidence: verified
owner: vfeenstr
responsibility: The SQLite run history beside the design store — packet
  issuances and verification runs. Appended per run, never committed, losing
  it loses history not design.
provides:
- seam:run-store
owns_data:
- data:packet-issuance
- data:verification-run
implemented_by:
- absicht#src/absicht/runstore.py
---
