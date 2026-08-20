---
id: component:codec
title: codec
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Spells records as YAML front matter plus Markdown body and
  back. The only layer that knows how a record looks on disk, which is what
  keeps the file format swappable.
parent: component:ab
implemented_by:
- absicht#src/absicht/codec.py
relates:
- to: library:pydantic
  type: depends_on
- to: library:pyyaml
  type: depends_on
- to: constraint:layer-stack
  type: constrained_by
- to: constraint:slug-no-underscore
  type: constrained_by
---
