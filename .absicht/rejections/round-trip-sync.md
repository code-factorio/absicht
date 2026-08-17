---
id: rejection:round-trip-sync
title: Round-trip sync with every provider
state: specified
confidence: reviewed
owner: vfeenstr
rejected_on: 2026-08-15
milestone: milestone:foundations
---

The store is files, one direction: authored, validated, folded, rendered.
Round-trip sync with every external tool multiplies the surface that can
disagree with the store, and each adapter becomes its own maintenance
project. Export where needed; never import authority.
