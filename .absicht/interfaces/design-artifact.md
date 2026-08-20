---
id: interface:design-artifact
title: The design artifact
state: specified
confidence: verified
owner: vfeenstr
style: file
declared_by: component:build
contract: .absicht/build/design.json
implemented_by:
- absicht#tests/test_build.py
---

The fold of the whole store into one normalized JSON document. Everything
downstream consumes this and nothing else, which is what makes the renderer,
the packet and verify testable without a filesystem store. Deterministic and
disposable — never committed.
