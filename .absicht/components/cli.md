---
id: component:cli
title: cli
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: The typer adapter — resolves arguments, calls the library,
  renders the result. No business logic, no print outside rendering, no
  sys.exit in the core; --json on every command from day one.
parent: component:ab
implemented_by:
- absicht#src/absicht/cli/
relates:
- to: req:agent-surface
  type: implements
- to: library:typer
  type: depends_on
- to: constraint:layer-stack
  type: constrained_by
- to: quality:additive-json
  type: satisfies
- to: quality:offline-operation
  type: satisfies
---
