---
id: seam:record-format
title: On-disk record format
state: specified
confidence: verified
owner: vfeenstr
style: schema
provider: component:codec
contract: schema/
carries:
- data:element-record
verified_by:
- tests/test_codec.py
---

One element per file, filename <slug>.md, YAML front matter carrying every
model field except source and body, Markdown body verbatim after it. The
consumers are human authors and schema-aware editors, not other modules —
load reads records through codec and never the bytes. system.yaml and
layout.yaml are plain YAML singletons.
