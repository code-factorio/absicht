---
id: req:build-artifact
title: Fold the store into one artifact
state: specified
confidence: verified
owner: vfeenstr
statement: The store must fold into one normalized, deterministic,
  format-versioned JSON document, which is disposable.
rationale: Everything downstream consumes it and nothing else, so renderer,
  packet and verify run without a filesystem store.
priority: must
actors:
- actor:agent
relates:
- to: goal:intent-survives
  type: derives_from
---
