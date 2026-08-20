---
id: behavior:reconciliation-fires
title: Nightly reconciliation
state: observed
confidence: assumed
owner: sam
trigger: The clock reaches 02:00 in the billing region.
observations:
- id: behavior:reconciliation-fires#obs-1
  statement: Every bill from the day before is compared against the provider.
  at: component:legacy-billing
  outcome: must
- id: behavior:reconciliation-fires#obs-2
  statement: A row lands in the shadow report for each mismatch.
  at: component:shadow-report
  outcome: must
relates:
- to: req:audit-trail
  type: realizes
---
This is what the code does. Why it runs at 02:00, and who reads the report,
nobody could say.
