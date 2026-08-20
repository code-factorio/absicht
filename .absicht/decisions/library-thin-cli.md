---
id: decision:library-thin-cli
title: A library with a thin CLI, from the first commit
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: A CLI you plan to extract a library from later never gets extracted
  cleanly, and agents are the primary consumer anyway.
choice: absicht is a library with a thin CLI over it, from the first commit.
consequences:
- No business logic in the CLI layer, no print outside rendering, no sys.exit in
  the core; everything returns values.
- '`--json` on every command from day one.'
- The eventual web and MCP surfaces become a week rather than a rewrite.
alternatives:
- A CLI to extract a library from later, an extraction that never happens
  cleanly.
applies_to:
- component:cli
decided_on: 2026-08-15
---

## Context

Not a CLI to extract a library from later — that extraction never happens
cleanly, and agents are the primary consumer anyway.

## Consequences

No business logic in the CLI layer, no print outside rendering, no sys.exit
in the core, everything returns values. `--json` on every command from day
one. The eventual web and MCP surfaces become a week rather than a rewrite.
