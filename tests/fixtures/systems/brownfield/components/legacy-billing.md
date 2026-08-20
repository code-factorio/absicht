---
id: component:legacy-billing
title: Billing engine
state: observed
confidence: assumed
owner: sam
level: container
responsibility: Turn orders into bills. Read from the code, not from a spec.
technology: Perl 5
parent: component:legacy
implemented_by:
- acme#billing
relates:
- to: req:audit-trail
  type: implements
- to: external:payment-api
  type: calls
  description: settles and refunds
  technology: HTTPS/JSON
---
