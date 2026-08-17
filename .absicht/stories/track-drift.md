---
id: story:track-drift
title: Track drift
state: specified
confidence: reviewed
owner: vfeenstr
actor: designer
outcome: which units are behind the design, by how much
satisfies:
- requirement:track-implementation
acceptance:
- id: story:track-drift#ac-1
  given:
  - a unit whose watermark is behind design head
  when: the designer runs ab status --fail-on-drift
  then:
  - the run exits FINDINGS naming the unit and the gap
- id: story:track-drift#ac-2
  kind: structural
  statement: stamping moves at and design_rev from the commit that lands work
  touches:
  - component:markers
---
