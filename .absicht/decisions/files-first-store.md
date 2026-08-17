---
id: decision:files-first-store
title: Files first, build artifact second
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-15
reversibility: costly
applies_to:
- component:codec
- component:load
- component:build
---

## Context

The store is written to by agents. Diffs, git merge-file and pull-request
review are the mechanisms that keep a machine-written store honest; a
database or an editor-first surface removes all three.

## Consequences

`.absicht/` is the authoring and review surface. `ab build` folds the tree
into one normalized JSON document and everything downstream consumes that
and nothing else — same shape as Rohrpost's log-to-tickets fold. The artifact
is deterministic, schema-versioned and disposable.
