---
id: actor:designer
title: Designer
state: specified
confidence: reviewed
owner: vfeenstr
actor_kind: person
goals:
- Write down why the system is shaped this way, what it must not do, and what
  was deliberately left open.
- Hand one slice of work to somebody else without explaining the whole system.
- Review the design the way code is reviewed, as a diff in a pull request.
---

Not a product looking for a market — a tool its author needs on Monday.
`.absicht/` is the authoring and review surface, because diffs,
`git merge-file` and pull-request review are what keep the store honest when
agents write to it.
