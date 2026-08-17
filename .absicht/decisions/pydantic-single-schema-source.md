---
id: decision:pydantic-single-schema-source
title: The schema lives in exactly one place
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-15
reversibility: costly
applies_to:
- component:models
- component:schema
---

## Context

An earlier draft said msgspec structs under `model/`. pydantic won on
validators-at-parse-time and generated JSON Schema; see
`rejection:msgspec-model-dir`.

## Consequences

The pydantic models in `absicht.models` are the one source. The validator,
the JSON Schema in `schema/` and the reference docs are generated from them,
so no three artefacts can drift. Committing the JSON Schema gives YAML
editors autocomplete and inline errors — most of what an authoring UI would
have bought. Every artifact carries `schema_version`.
