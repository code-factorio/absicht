---
id: component:cli
title: cli
state: specified
confidence: verified
owner: vfeenstr
responsibility: The typer adapter — resolves arguments, calls the library,
  renders the result. No business logic, no print outside rendering, no
  sys.exit in the core; --json on every command from day one.
consumes:
- external:typer
provides:
- seam:json-envelope
implemented_by:
- absicht#src/absicht/cli/
---
