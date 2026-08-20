---
id: goal:bounded-context
title: An agent gets bounded context, not a repo and a sentence
state: specified
confidence: reviewed
owner: vfeenstr
outcome: >-
  An implementer starts a slice with this scope, these contracts and these
  rules that must hold, instead of a repo and a sentence.
measure: findings `ab verify` reports on work returned against a packet
target: no scope leakage and nothing built on an `unknown`
stakeholders:
- actor:agent
- actor:designer
---

The missing input is not more context — it is *bounded* context: this scope,
these contracts, these rules that must hold, these choices you may make
freely, these things we genuinely have not decided. If a hand-written packet
does not measurably improve what an agent produces, the rest of this is
decoration and the project should stop there.
