---
id: story:review-a-design-change
title: Review a design change
state: specified
confidence: reviewed
owner: vfeenstr
actor: designer
outcome: what changed in the design, as elements rather than lines
satisfies:
- requirement:track-implementation
acceptance:
- id: story:review-a-design-change#ac-1
  when: the designer runs ab diff on two revisions
  then:
  - added decisions, moved seams and state transitions are listed
- id: story:review-a-design-change#ac-2
  kind: structural
  statement: no artifact is written for either side of the comparison
  touches:
  - component:diff
---
