---
id: component:load
title: load
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Walks the store directory into per-kind tuples, plus notes
  beside the design. The only layer that knows a store is a directory layout;
  sets source on every record.
parent: component:ab
implemented_by:
- absicht#src/absicht/load.py
relates:
- to: interface:record-format
  type: calls
- to: resource:store-tree
  type: depends_on
---
