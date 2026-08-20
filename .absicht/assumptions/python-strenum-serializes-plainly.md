---
id: assumption:python-strenum-serializes-plainly
title: StrEnum and StringConstraints behave as the model assumes
state: specified
confidence: reviewed
owner: vfeenstr
statement: A StrEnum member serializes as its plain string value through
  pydantic, and an Annotated StringConstraints pattern is enforced when the
  record is parsed.
verified_on: 2026-08-15
expires_on: 2027-02-15
invalidates:
- component:codec
- component:models
- constraint:slug-no-underscore
---

StrEnum members serialize as their plain string values through pydantic.

Annotated StringConstraints enforce the Ref, Slug and ObservationId patterns
at parse time.
