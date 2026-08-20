---
id: constraint:layer-stack
title: A layer stack, enforced by import contracts
state: specified
confidence: reviewed
owner: vfeenstr
statement: Nothing below codec must know how a record is spelled on disk, and
  nothing below cli must know it is run from a terminal.
constraint_kind: technical
imposed_by: the import-linter contracts in pyproject.toml
---

A module may import anything below it in the stack and nothing above it. The
contracts name every layer, so a layer that exists and is not listed stops
being covered.
