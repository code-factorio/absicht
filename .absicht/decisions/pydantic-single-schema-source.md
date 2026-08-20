---
id: decision:pydantic-single-schema-source
title: The schema lives in exactly one place
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: An earlier draft said msgspec structs under `model/`, and pydantic won
  on validators that run at parse time and on JSON Schema generated from the
  same types.
choice: The pydantic models in `absicht.models` are the one source of the schema,
  and every other artefact is generated from them.
consequences:
- The validator, the JSON Schema in `schema/` and the reference docs are
  generated from the models, so no three artefacts can drift.
- Committing the JSON Schema gives YAML editors autocomplete and inline errors,
  which is most of what an authoring UI would have bought.
- Every artifact carries `format_version`.
alternatives:
- msgspec structs under `model/`; see `rejection:msgspec-model-dir`.
applies_to:
- component:models
- component:schema
decided_on: 2026-08-15
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
have bought. Every artifact carries `format_version`.
