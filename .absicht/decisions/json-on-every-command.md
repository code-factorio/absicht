---
id: decision:json-on-every-command
title: --json is accepted on the command, not only ahead of it
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: Typer only parses a group's options before the subcommand name, so the
  global `--json` made `ab check --json` a usage error — the wrong way round
  for agents and CI, which append flags to a command they have composed.
choice: Every command declares `--json` itself, so the flag means the same thing
  ahead of the subcommand, on it, or in both places at once.
consequences:
- Where a command also has `--format` with a json member, an explicit `--format`
  wins.
- '`--json` selects json only when `--format` was left at its default: a
  shorthand, never an override.'
- The argument is written out in full in `docs/adr/0001`.
alternatives:
- Leaving `--json` an option of the group only, which keeps `ab check --json` a
  usage error.
applies_to:
- component:cli
decided_on: 2026-08-16
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
