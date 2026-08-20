---
id: decision:store-mode-by-file-type
title: The store's location is a mode, and .absicht carries it
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: A single-repo project wants the design beside the code; a composite ends
  up with the design in a repo of its own, because a ticket belongs to a
  codebase but a design belongs to a system and a system is a composition.
choice: The name `.absicht` carries the mode — a directory is embedded, a file is
  reference.
consequences:
- One name is one directory entry, so the modes are exclusive by filesystem, not
  by convention.
- '`design.yaml` pins the units it composes, like a lockfile, either way.'
- A unit is anything with its own release cadence, not anything with its own
  deployment — a library, a service, a component inside a monolith.
alternatives:
- A setting that names the mode, which convention rather than the filesystem has
  to keep exclusive.
applies_to:
- component:init
- component:markers
decided_on: 2026-08-15
---

## Context

A single-repo project wants the design beside the code; a composite ends up
with the design in a repo of its own, because a ticket belongs to a
codebase but a design belongs to a system and a system is a composition.

## Consequences

A directory is embedded, a file is reference. One name is one directory
entry, so the modes are exclusive by filesystem, not by convention.
`design.yaml` pins the units it composes, like a lockfile, either way. A
unit is anything with its own release cadence, not anything with its own
deployment — a library, a service, a component inside a monolith.
