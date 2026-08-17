---
id: requirement:agent-surface
title: Every command speaks to agents
state: specified
confidence: verified
owner: vfeenstr
realized_by:
- component:cli
constrains:
- seam:json-envelope
---

--json on every command and on the command itself, diagnostics on stderr, a
meaningful exit code (findings vs usage vs internal vs schema mismatch), and
no command needing a terminal. Agents are the primary consumer; the terminal
is the secondary one.
