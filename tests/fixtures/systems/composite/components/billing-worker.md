---
id: component:billing-worker
title: Billing worker
state: specified
confidence: reviewed
owner: kim
level: container
responsibility: Turn a settled order into an invoice.
technology: Python 3.14
parent: component:acme
implemented_by:
- billing#worker
relates:
- to: req:issue-invoice
  type: implements
- to: interface:invoice-events
  type: calls
  description: consumes settlements
  technology: JSON over the event bus
---
The consumer of the seam lives in the other repository: unit membership is
derivable from `implemented_by` alone, which is what the multi-repo commands
lean on.
