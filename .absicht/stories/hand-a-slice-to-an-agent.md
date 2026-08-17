---
id: story:hand-a-slice-to-an-agent
title: Hand a slice to an agent
state: specified
confidence: reviewed
owner: vfeenstr
actor: designer
outcome: a sealed brief the agent can work from offline
satisfies:
- requirement:bounded-handoff
acceptance:
- id: story:hand-a-slice-to-an-agent#ac-1
  given:
  - a milestone with scope
  when: the designer runs ab packet with --seal and a target agent
  then:
  - packet.md, packet.lock and the .feature files are written
  - the issuance is recorded in the run store
- id: story:hand-a-slice-to-an-agent#ac-2
  kind: structural
  statement: the packet carries must-satisfy and must-not-break behavior lists
  touches:
  - component:packet
- id: story:hand-a-slice-to-an-agent#ac-3
  given:
  - the sealed packet directory
  when: the agent works without the design store
  then:
  - everything needed is in the packet
---
