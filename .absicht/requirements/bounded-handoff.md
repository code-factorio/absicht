---
id: req:bounded-handoff
title: Hand an agent a bounded packet
state: specified
confidence: reviewed
owner: vfeenstr
statement: An agent must get one bounded packet that carries the milestone
  scope and one ring around it, and nothing else.
priority: must
actors:
- actor:agent
relates:
- to: goal:bounded-context
  type: derives_from
---

Milestone scope at full fidelity, one ring of neighbouring contracts, the
decisions and quality requirements that must hold, explicit freedoms, known
unknowns, the rejections that must not be re-proposed — and two behavior
lists: the behaviors this slice must satisfy and the active behaviors it must
not break. Sealed with design rev plus observations digest so verify runs
offline. Issuance is recorded in the local run store.
