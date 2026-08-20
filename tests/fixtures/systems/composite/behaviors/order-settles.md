---
id: behavior:order-settles
title: An order settles
state: specified
confidence: reviewed
owner: kim
trigger: The payment provider reports a charge as settled.
observations:
- id: behavior:order-settles#obs-1
  statement: An OrderSettled event is published.
  at: interface:invoice-events
  outcome: must
- id: behavior:order-settles#obs-2
  statement: An invoice exists for the order.
  at: component:billing-worker
  outcome: must
relates:
- to: req:issue-invoice
  type: realizes
---
