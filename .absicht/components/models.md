---
id: component:models
title: models
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: The element records and enums. Imports nothing of ours; a
  field exists only if something computes over it, everything else is prose in
  body.
parent: component:ab
implemented_by:
- absicht#src/absicht/models/
relates:
- to: req:model-elements
  type: implements
- to: library:pydantic
  type: depends_on
- to: constraint:python-314
  type: constrained_by
- to: constraint:layer-stack
  type: constrained_by
---
