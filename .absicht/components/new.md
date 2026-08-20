---
id: component:new
title: new
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Scaffolding, not a wizard — writes the minimal valid
  instance of a kind with a deterministic id from the slug. Placeholders mark
  required fields the model has no defaults for.
parent: component:ab
implemented_by:
- absicht#src/absicht/new.py
relates:
- to: req:author-store
  type: implements
---
