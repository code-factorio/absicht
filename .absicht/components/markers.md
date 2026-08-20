---
id: component:markers
title: markers
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Writes, checks and stamps the .absicht discovery files in
  implementing repos. The store stays authoritative; markers are regenerable
  hints.
parent: component:ab
implemented_by:
- absicht#src/absicht/markers.py
relates:
- to: req:track-implementation
  type: implements
- to: resource:git-repository
  type: depends_on
---
