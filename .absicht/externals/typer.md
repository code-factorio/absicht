---
id: external:typer
title: typer
state: specified
confidence: reviewed
owner: vfeenstr
external_kind: library
version: '>=0.27.1'
assumptions:
- Built on click, so options declared on a command parse after the subcommand
  name — the premise ADR-0001 rests on for --json on the command itself.
- Enum arguments (kinds, formats, severities) render their value sets in help.
verified_on: 2026-08-15
verified_by: vfeenstr
---
