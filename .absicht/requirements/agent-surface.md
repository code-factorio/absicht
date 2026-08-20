---
id: req:agent-surface
title: Every command speaks to agents
state: specified
confidence: verified
owner: vfeenstr
statement: Every command must offer --json, put diagnostics on stderr, return a
  meaningful exit code, and run without a terminal.
rationale: Agents are the primary consumer; the terminal is the secondary one.
priority: must
actors:
- actor:agent
relates:
- to: goal:design-is-queryable
  type: derives_from
---

--json on every command and on the command itself, diagnostics on stderr, a
meaningful exit code (findings vs usage vs internal vs schema mismatch), and
no command needing a terminal.
