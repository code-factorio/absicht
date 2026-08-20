---
id: req:query-design
title: Query the design
state: specified
confidence: verified
owner: vfeenstr
statement: A designer or an agent must be able to answer a question about the
  design without reading it end to end.
priority: must
actors:
- actor:designer
- actor:agent
relates:
- to: goal:design-is-queryable
  type: derives_from
---

show resolves one element both ways, list filters by state, owner, tag,
milestone, lifecycle and derived scope, gaps returns the unfinished worklist
with inherited owners, trace walks requirement to component to interface to
decision in either direction. ids format for piping, json for agents.
