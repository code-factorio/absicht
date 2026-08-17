---
id: nfr:byte-identical-build
title: Generated output is byte-identical
state: specified
confidence: verified
owner: vfeenstr
attribute: operability
scope:
- component:build
- component:diagram
- component:gherkin
stimulus: the same store built twice from clean checkouts, PYTHONHASHSEED varied
measure: byte-diff of design.json, the site's SVGs and the .feature files
target: zero bytes differ
evidence:
- tests/test_build.py determinism cases
---

Determinism is an invariant with its own reason to exist: artifacts are
regenerated rather than stored, and a diagram that reshuffles on every
regeneration never builds spatial memory.
