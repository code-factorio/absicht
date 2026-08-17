---
id: component:init
title: init
state: specified
confidence: verified
owner: vfeenstr
responsibility: Chooses a store mode explicitly and scaffolds system.yaml —
  the one file a store cannot derive. Never overwrites; one name is one
  directory entry, so the modes are exclusive by filesystem.
implemented_by:
- absicht#src/absicht/init.py
---
