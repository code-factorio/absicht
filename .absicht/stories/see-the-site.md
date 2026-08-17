---
id: story:see-the-site
title: See the site
state: specified
confidence: reviewed
owner: vfeenstr
actor: designer
outcome: the whole design browsable, regenerated on demand
satisfies:
- requirement:render-site
acceptance:
- id: story:see-the-site#ac-1
  when: the site regenerates with a pinned layout
  then:
  - the SVG bytes are identical to the previous run
- id: story:see-the-site#ac-2
  kind: structural
  statement: every kind has pages, the note inbox included
  touches:
  - component:render
---
