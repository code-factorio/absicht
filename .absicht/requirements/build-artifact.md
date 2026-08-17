---
id: requirement:build-artifact
title: Fold the store into one artifact
state: specified
confidence: verified
owner: vfeenstr
realized_by:
- component:build
constrains:
- seam:design-artifact
---

One normalized JSON document, deterministic, schema-versioned, disposable.
Everything downstream consumes it and nothing else, so renderer, packet and
verify run without a filesystem store.
