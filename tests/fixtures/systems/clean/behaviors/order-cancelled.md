---
id: behavior:order-cancelled
title: Cancelling an unshipped order
state: specified
confidence: reviewed
owner: dana
trigger: The customer clicks Cancel on an order that has not shipped.
observations:
- id: behavior:order-cancelled#obs-1
  statement: The order reads cancelled.
  at: component:orders
  outcome: must
  timing: immediate
- id: behavior:order-cancelled#obs-2
  statement: No entry for the order remains in the cache.
  at: resource:order-cache
  outcome: must_not
- id: behavior:order-cancelled#obs-3
  statement: An OrderCancelled event carries the reason the customer gave.
  at: resource:order-stream
  outcome: should
relates:
- to: req:cancel-orders
  type: realizes
---
