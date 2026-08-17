---
id: decision:run-store-not-in-git
title: Runs live beside the store, not in it
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-16
reversibility: costly
applies_to:
- component:runstore
---

## Context

Packets and verification runs are machine-generated, appended per run and
never reviewed as a diff. Committing them adds volume proportional to agent
activity for no benefit — the same argument that put Rohrpost's bus state in
SQLite rather than the log.

## Consequences

SQLite at `.absicht/build/runs.db`, inside the already-gitignored build
directory. The packet artifact is deterministic from milestone plus design
rev and is regenerated rather than stored. Losing the run store loses
history, not design.
