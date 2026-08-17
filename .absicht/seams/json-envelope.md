---
id: seam:json-envelope
title: The --json envelope
state: specified
confidence: reviewed
owner: vfeenstr
style: call
provider: component:cli
verified_by:
- tests/test_cli.py
---

Every command's --json output is one object with schema_version at the top
level plus command-specific fields. The consumers are agents and CI, which
parse it — so a field never changes meaning; it gets deprecated and a new one
appears. An explicit --format json wins over --json, which selects the json
member only when --format was left at its default (ADR-0001).
