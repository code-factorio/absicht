---
id: assumption:typer-parses-command-options
title: typer parses an option declared on the command
state: specified
confidence: reviewed
owner: vfeenstr
statement: typer is built on click, so an option declared on a command parses
  after the subcommand name, which is what lets `--json` sit on the command
  itself.
verified_on: 2026-08-15
expires_on: 2027-02-15
invalidates:
- component:cli
- req:agent-surface
---

Built on click, so options declared on a command parse after the subcommand
name — the premise `decision:json-on-every-command` (ADR-0001) rests on for
--json on the command itself.

Enum arguments (kinds, formats, severities) render their value sets in help.
