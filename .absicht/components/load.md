---
id: component:load
title: load
state: specified
confidence: verified
owner: vfeenstr
responsibility: Walks the store directory into per-kind tuples, plus notes
  beside the design. The only layer that knows a store is a directory layout;
  sets source on every record.
consumes:
- seam:record-format
implemented_by:
- absicht#src/absicht/load.py
---
