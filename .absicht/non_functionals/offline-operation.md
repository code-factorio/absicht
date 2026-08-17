---
id: nfr:offline-operation
title: No network, no LLM, anywhere
state: specified
confidence: verified
owner: vfeenstr
attribute: operability
scope:
- component:cli
stimulus: ab runs in an airgapped CI runner against a fetched packet
measure: network calls and model invocations made
target: none
evidence:
- the dependency tree contains no HTTP client
---

verify must run offline in CI, in somebody else's repo; authoring,
validation, rendering, planning and packets all work without an LLM.
