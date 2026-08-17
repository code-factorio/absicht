---
id: decision:capture-on-touch
title: Capture on touch, never backfill
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-15
reversibility: cheap
applies_to:
- component:models
---

## Context

A backfill project that records the whole design of an existing system never
finishes, and its partial output reads as failure when it is really an
honest measurement.

## Consequences

Design truth accretes along the path of real work. A brownfield import that
lands 90% `observed` is telling the truth, not failing — `observed` is the
brownfield state and the reason import works at all. The next packet
against a component is what compares design to reality.
