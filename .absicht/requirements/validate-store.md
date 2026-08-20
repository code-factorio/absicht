---
id: req:validate-store
title: Validate the store in three layers
state: specified
confidence: verified
owner: vfeenstr
statement: check must validate the store in three layers — schema, integrity
  and policy.
priority: must
actors:
- actor:designer
- actor:ci
relates:
- to: goal:intent-survives
  type: derives_from
---

Schema (fields, types, patterns), integrity (refs resolve, no cycles,
observations anchored), policy (unknowns owned, requirements realized,
one_way decisions argued, external assumptions current) — plus the addendum
rules: interfaces stay off resources, observations point at the right kinds,
composition and supersession stay acyclic, promoted notes resolve. Findings
at error severity exit FINDINGS; advisory-only exits zero.
