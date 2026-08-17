---
id: behavior:queries-answer-in-json
title: Queries answer in json
state: specified
lifecycle: active
owner: vfeenstr
trigger: A command runs with --json.
realizes:
- requirement:agent-surface
observations:
- id: behavior:queries-answer-in-json#obs-1
  statement: The output is one object with schema_version at the top level
  at: component:cli
  outcome: must
  timing: immediate
- id: behavior:queries-answer-in-json#obs-2
  statement: Diagnostics stay on stderr
  at: component:cli
  outcome: must
  timing: immediate
- id: behavior:queries-answer-in-json#obs-3
  statement: The envelope's schema version travels in --version and every
    artifact
  at: seam:json-envelope
  outcome: must
  timing: immediate
---
