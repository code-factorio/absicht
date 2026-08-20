---
id: decision:files-first-store
title: Files first, build artifact second
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: The store is written to by agents, and diffs, git merge-file and
  pull-request review are the mechanisms that keep a machine-written store
  honest.
choice: The store is a tree of files that is authored and reviewed, and `ab
  build` folds it into one normalized JSON document that everything downstream
  consumes.
consequences:
- '`.absicht/` is the authoring and review surface.'
- Everything downstream consumes the build artifact and nothing else.
- The artifact is deterministic, format-versioned and disposable.
alternatives:
- A database, which removes diffs, git merge-file and pull-request review.
- An editor-first surface, which removes the same three.
applies_to:
- component:codec
- component:load
- component:build
decided_on: 2026-08-15
---

## Context

The store is written to by agents. Diffs, git merge-file and pull-request
review are the mechanisms that keep a machine-written store honest; a
database or an editor-first surface removes all three.

## Consequences

`.absicht/` is the authoring and review surface. `ab build` folds the tree
into one normalized JSON document and everything downstream consumes that
and nothing else — same shape as Rohrpost's log-to-tickets fold. The artifact
is deterministic, format-versioned and disposable.
