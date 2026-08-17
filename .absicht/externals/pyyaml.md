---
id: external:pyyaml
title: PyYAML
state: specified
confidence: reviewed
owner: vfeenstr
external_kind: library
version: '>=6.0.2'
assumptions:
- safe_load parses the front matter; insertion order survives, so the codec
  dumps fields in the model's own order and output stays byte-stable.
- Dates in front matter arrive as datetime.date, matching the model directly.
verified_on: 2026-08-15
verified_by: vfeenstr
---
