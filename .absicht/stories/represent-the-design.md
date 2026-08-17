---
id: story:represent-the-design
title: Represent the design in the store
state: constrained
owner: vfeenstr
actor: designer
outcome: the design that lived in docs/spec, docs/tasks and the ticket log is
  represented as store elements, and ab's own commands read it
acceptance:
- id: story:represent-the-design#ac-1
  when: the designer represents the system in the store
  then:
  - every element kind has at least one instance
  - ab check exits zero
- id: story:represent-the-design#ac-2
  kind: structural
  statement: the store carries the CLI surface, the model addendum and the gate
    rationale as requirements, behaviors and decisions
  touches:
  - seam:design-artifact
- id: story:represent-the-design#ac-3
  when: ab gaps runs against the completed store
  then:
  - the genuinely open questions appear as a worklist
---

absicht's own design is the most available honest test of the model: it has
real decisions, real rejections, real open questions and a command surface
that the store must be able to name. CONTEXT.md promised this dogfooding from
the start; this story is it happening.
