---
id: seam:run-store
title: The run store
state: specified
confidence: verified
owner: vfeenstr
style: schema
provider: component:runstore
consumers:
- component:packet
- component:verify
contract: .absicht/build/runs.db
carries:
- data:packet-issuance
- data:verification-run
verified_by:
- tests/test_runstore.py
---

SQLite beside the design store, inside the gitignored build directory. Two
tables matching the addendum's tuples: packet issuances and verification
runs. Machine-generated, appended per run, never reviewed as a diff.
