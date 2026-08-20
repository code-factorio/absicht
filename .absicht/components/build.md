---
id: component:build
title: build
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Loads and resolves the store, spells it as one normalized
  JSON document. Everything downstream reads the artifact and never the
  store, so this module is the one place the fold happens.
parent: component:ab
implemented_by:
- absicht#src/absicht/build.py
relates:
- to: req:build-artifact
  type: implements
- to: quality:byte-identical-build
  type: satisfies
---
