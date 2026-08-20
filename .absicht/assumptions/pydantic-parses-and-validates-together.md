---
id: assumption:pydantic-parses-and-validates-together
title: pydantic validates while it parses
state: specified
confidence: reviewed
owner: vfeenstr
statement: A frozen, extra=forbid pydantic record with model_validator(mode=after)
  turns an unknown key, a bad pattern and a bad shape into a parse error, so
  validation happens where the record is built and nowhere else.
verified_on: 2026-08-15
expires_on: 2027-02-15
invalidates:
- component:codec
- component:models
- component:schema
- constraint:layer-stack
---

frozen, extra=forbid records mean an unknown key or a bad pattern fails at
parse time inside codec/load, so the schema layer has little left to check.

model_validator(mode=after) runs during parsing, which is what lets shape
rules (observations anchored, must_not timing, identity fields) be parse
errors.

TypeAdapter into JSON Schema covers every record, so schema/ is generated and
never hand-maintained.
