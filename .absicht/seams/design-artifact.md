---
id: seam:design-artifact
title: The design artifact
state: specified
confidence: verified
owner: vfeenstr
style: schema
provider: component:build
consumers:
- component:render
- component:diagram
- component:packet
- component:verify
- component:status
- component:diff
contract: .absicht/build/design.json
carries:
- data:design
verified_by:
- tests/test_build.py
---

The fold of the whole store into one normalized JSON document. Everything
downstream consumes this and nothing else, which is what makes the renderer,
the packet and verify testable without a filesystem store. Deterministic and
disposable — never committed.
