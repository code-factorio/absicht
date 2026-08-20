---
id: assumption:pyyaml-preserves-order
title: PyYAML round-trips front matter in order
state: specified
confidence: reviewed
owner: vfeenstr
statement: PyYAML's safe_load reads the front matter with its insertion order
  intact, so a dump in the model's own field order is byte-stable.
verified_on: 2026-08-15
expires_on: 2027-02-15
invalidates:
- component:codec
- quality:byte-identical-build
---

safe_load parses the front matter; insertion order survives, so the codec
dumps fields in the model's own order and output stays byte-stable.

Dates in front matter arrive as datetime.date, matching the model directly.
