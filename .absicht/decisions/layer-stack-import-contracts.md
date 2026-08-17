---
id: decision:layer-stack-import-contracts
title: A layer stack, enforced by import contracts
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-15
reversibility: costly
applies_to:
- component:models
- component:codec
- component:load
- component:resolve
- component:check
- component:build
- component:render
- component:cli
---

## Context

Nothing below `codec` may know how a record is spelled on disk, or the file
format stops being swappable. Nothing below `cli` may know it is being run
from a terminal, or the core stops being reusable behind a web or MCP
surface.

## Consequences

pyproject's import-linter contracts name the stack; a module may import
anything below it and nothing above. A new module joins the list in the
commit that creates it — a layer that exists and is not listed makes the
contract silently stop covering it. `findings` and `git` sit near the bottom
as cross-cutting layers.
