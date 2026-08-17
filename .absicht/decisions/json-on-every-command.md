---
id: decision:json-on-every-command
title: --json is accepted on the command, not only ahead of it
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-16
reversibility: costly
applies_to:
- component:cli
---

## Context

Typer only parses a group's options before the subcommand name, so the
global `--json` made `ab check --json` a usage error. That is the wrong way
round for agents and CI, which append flags to a command they have composed.

## Consequences

Every command declares `--json` as well; the two positions — or both at once
— mean the same thing. Where a command also has `--format` with a json
member, an explicit `--format` wins and `--json` selects json only when
`--format` was left at its default. A shorthand, never an override. See
`docs/adr/0001`.
