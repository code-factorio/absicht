---
id: story:author-an-element
title: Author an element
state: specified
confidence: verified
owner: vfeenstr
actor: designer
outcome: a new element exists in the store, valid and owned
satisfies:
- requirement:author-store
acceptance:
- id: story:author-an-element#ac-1
  when: the designer runs ab new behavior order-placed with a title
  then:
  - behaviors/order-placed.md exists with id behavior:order-placed
  - its state is unknown until the designer says otherwise
- id: story:author-an-element#ac-2
  kind: structural
  statement: an invalid slug is a usage error and writes nothing
  touches:
  - component:cli
---
