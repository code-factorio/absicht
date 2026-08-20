---
id: component:diff
title: diff
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Builds the Design at two revisions in memory and compares
  element by element — decisions added, interfaces whose contract moved, state
  transitions. No artifact is written for either side.
parent: component:ab
implemented_by:
- absicht#src/absicht/diff.py
relates:
- to: req:track-implementation
  type: implements
- to: interface:design-artifact
  type: calls
---
