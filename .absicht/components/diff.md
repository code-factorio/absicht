---
id: component:diff
title: diff
state: specified
confidence: verified
owner: vfeenstr
responsibility: Builds the Design at two revisions in memory and compares
  element by element — decisions added, seams whose contract moved, state
  transitions. No artifact is written for either side.
consumes:
- seam:design-artifact
implemented_by:
- absicht#src/absicht/diff.py
---
