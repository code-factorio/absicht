---
id: actor:agent
title: Coding agent
state: specified
confidence: reviewed
owner: vfeenstr
actor_kind: system
goals:
- Act on one slice of work without reading the whole system.
- Know which choices may be made freely and which are already decided.
- Ask instead of inventing where the design says nothing.
---

Agents read code well and infer intent badly. Handing one a repo and a
sentence produces plausible work that violates constraints nobody wrote down.
Agents are the primary consumer of every command; the terminal is the
secondary one.
