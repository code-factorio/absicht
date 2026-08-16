---
id: behavior:reconciliation-fires
title: Nightly reconciliation fires
state: observed
trigger: The nightly reconciliation job runs.
observations:
- id: behavior:reconciliation-fires#obs-1
  statement: A mismatch row is written to the shadow report
  at: component:shadow-report
  outcome: must
  timing: immediate
- id: behavior:reconciliation-fires#obs-2
  statement: The legacy billing job retries three times before giving up
  at: component:legacy-billing
  outcome: must
---
