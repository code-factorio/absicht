---
id: story:inspect-the-design
title: Inspect the design
state: specified
confidence: verified
owner: vfeenstr
actor: designer
outcome: one element or one worklist, without reading files
satisfies:
- requirement:query-design
acceptance:
- id: story:inspect-the-design#ac-1
  when: the designer runs ab list behavior --format ids
  then:
  - one id per line, pipeable
- id: story:inspect-the-design#ac-2
  when: the designer runs ab show on a behavior
  then:
  - derived facts appear — scope, composition, superseded_by
  - no derived fact is stored in the file
- id: story:inspect-the-design#ac-3
  when: the designer traces a requirement to a component
  then:
  - paths render as element chains in either direction
---
