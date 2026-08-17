---
id: component:build
title: build
state: specified
confidence: verified
owner: vfeenstr
responsibility: Loads and resolves the store, spells it as one normalized
  JSON document. Everything downstream reads the artifact and never the
  store, so this module is the one place the fold happens.
provides:
- seam:design-artifact
owns_data:
- data:design
implemented_by:
- absicht#src/absicht/build.py
---
