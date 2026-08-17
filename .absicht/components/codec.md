---
id: component:codec
title: codec
state: specified
confidence: verified
owner: vfeenstr
responsibility: Spells records as YAML front matter plus Markdown body and
  back. The only layer that knows how a record looks on disk, which is what
  keeps the file format swappable.
consumes:
- external:pydantic
- external:pyyaml
provides:
- seam:record-format
owns_data:
- data:element-record
implemented_by:
- absicht#src/absicht/codec.py
---
