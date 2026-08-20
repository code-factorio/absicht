---
id: component:init
title: init
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Chooses a store mode explicitly and scaffolds design.yaml —
  the one file a store cannot derive. Never overwrites; one name is one
  directory entry, so the modes are exclusive by filesystem.
parent: component:ab
implemented_by:
- absicht#src/absicht/init.py
relates:
- to: req:author-store
  type: implements
---
