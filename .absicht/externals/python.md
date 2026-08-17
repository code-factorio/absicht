---
id: external:python
title: Python
state: specified
confidence: reviewed
owner: vfeenstr
external_kind: runtime
version: '>=3.14'
assumptions:
- StrEnum members serialize as their plain string values through pydantic.
- Annotated StringConstraints enforce the Ref, Slug, CriterionId and
  ObservationId patterns at parse time.
verified_on: 2026-08-15
verified_by: vfeenstr
---
