---
id: component:models
title: models
state: specified
confidence: verified
owner: vfeenstr
responsibility: The element records and enums. Imports nothing of ours; a
  field exists only if something computes over it, everything else is prose in
  body.
consumes:
- external:python
- external:pydantic
owns_data:
- data:element-record
implemented_by:
- absicht#src/absicht/models.py
---
