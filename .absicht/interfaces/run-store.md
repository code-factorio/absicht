---
id: interface:run-store
title: The run store
state: specified
confidence: verified
owner: vfeenstr
style: file
declared_by: component:runstore
contract: .absicht/build/runs.db
implemented_by:
- absicht#tests/test_runstore.py
---

SQLite beside the design store, inside the gitignored build directory. Two
tables matching the addendum's tuples: packet issuances and verification
runs. Machine-generated, appended per run, never reviewed as a diff.
