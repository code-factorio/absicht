---
id: decision:store-mode-by-file-type
title: The store's location is a mode, and .absicht carries it
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-15
reversibility: costly
applies_to:
- component:init
- component:markers
---

## Context

A single-repo project wants the design beside the code; a composite ends up
with the design in a repo of its own, because a ticket belongs to a
codebase but a design belongs to a system and a system is a composition.

## Consequences

A directory is embedded, a file is reference. One name is one directory
entry, so the modes are exclusive by filesystem, not by convention.
`system.yaml` pins the units it composes, like a lockfile, either way. A
unit is anything with its own release cadence, not anything with its own
deployment — a library, a service, a component inside a monolith.
