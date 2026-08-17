---
id: external:pydantic
title: pydantic
state: specified
confidence: reviewed
owner: vfeenstr
external_kind: library
version: '>=2.13.4'
assumptions:
- frozen, extra=forbid records mean an unknown key or a bad pattern fails at
  parse time inside codec/load, so the schema layer has little left to check.
- model_validator(mode=after) runs during parsing, which is what lets shape
  rules (criteria anchored, must_not timing, identity fields) be parse errors.
- TypeAdapter into JSON Schema covers every record, so schema/ is generated
  and never hand-maintained.
verified_on: 2026-08-15
verified_by: vfeenstr
---
