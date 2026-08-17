---
id: story:validate-a-store
title: Validate a store
state: specified
confidence: verified
owner: vfeenstr
actor: designer
outcome: the store's broken parts are named, or it is clean
satisfies:
- requirement:validate-store
acceptance:
- id: story:validate-a-store#ac-1
  given:
  - a store with a dangling reference
  when: the designer runs ab check
  then:
  - the run exits FINDINGS
  - an error finding names the rule and the file
- id: story:validate-a-store#ac-2
  when: the designer runs ab check on a clean store
  then:
  - the run exits zero
  - advisory findings may remain
- id: story:validate-a-store#ac-3
  kind: structural
  statement: --strict promotes warnings for the exit decision only
  touches:
  - component:check
---
