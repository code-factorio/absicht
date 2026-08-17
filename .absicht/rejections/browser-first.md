---
id: rejection:browser-first
title: Browser-first surfaces
state: specified
confidence: reviewed
owner: vfeenstr
applies_to:
- component:render
rejected_on: 2026-08-16
milestone: milestone:addendum-model
---

A design that is only reachable through the browser is a defect: roughly 95%
of reads are machine reads through `ab --json`, an MCP server, or a skill.
The browser is one projection of the model and the least important consumer
of it.
