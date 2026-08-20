---
id: goal:design-is-queryable
title: The design answers a question without being read end to end
state: specified
confidence: reviewed
owner: vfeenstr
outcome: >-
  A question about scope, contracts, trace or gaps is answered by one command,
  by a person or by an agent, without the store being read end to end.
measure: >-
  design questions `ab show`, `ab list`, `ab trace` and `ab gaps` cannot
  answer
target: none
stakeholders:
- actor:agent
- actor:designer
---

None of the scattered design is queryable, and none of it is linked. Files in
a repo, validated, rendered, queried, are the answer this project makes to
that, and `--json` is on every command because agents are the primary
consumer.
