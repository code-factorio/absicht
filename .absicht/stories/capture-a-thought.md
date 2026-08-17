---
id: story:capture-a-thought
title: Capture a thought
state: specified
confidence: verified
owner: vfeenstr
actor: designer
outcome: a half-formed idea is kept without classifying it
satisfies:
- requirement:capture-notes
acceptance:
- id: story:capture-a-thought#ac-1
  when: the designer adds a note with --ref
  then:
  - it lists in the inbox with its age
- id: story:capture-a-thought#ac-2
  when: the designer promotes the note
  then:
  - the element exists with the promoted_to recorded on the note
  - the inbox line is gone
- id: story:capture-a-thought#ac-3
  kind: structural
  statement: notes never enter the build artifact or a packet
  touches:
  - component:notes
---
