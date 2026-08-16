---
id: behavior:bad-timing
title: A must_not observation with a timing
state: specified
trigger: A file exercises the must_not-with-timing parse refusal.
observations:
- id: behavior:bad-timing#obs-1
  statement: A forbidden outcome is given a timing
  at: resource:audit-store
  outcome: must_not
  timing: immediate
---
