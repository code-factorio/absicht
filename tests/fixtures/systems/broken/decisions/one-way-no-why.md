---
id: decision:one-way-no-why
title: Store audit rows forever
state: constrained
confidence: reviewed
owner: dana
choice: Audit rows are never deleted.
applies_to:
- component:audits
decided_on: 2026-01-02
---
`policy/agency-undeclared`: `constrained` and no `reversibility`, so an agent
cannot judge whether to decide freely, propose first, or stop and ask. The
argument for the choice is also missing, which is what the empty consequences
say out loud.
