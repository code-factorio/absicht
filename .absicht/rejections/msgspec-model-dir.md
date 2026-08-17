---
id: rejection:msgspec-model-dir
title: msgspec structs under model/
state: specified
confidence: reviewed
owner: vfeenstr
applies_to:
- component:models
rejected_on: 2026-08-15
milestone: milestone:step-1-author-validate
---

An earlier draft spelled the schema as msgspec structs under `model/`.
pydantic won on validators that run at parse time and JSON Schema generated
from the same types; CONTEXT.md carried the stale claim until the addendum
conventions task killed it.
