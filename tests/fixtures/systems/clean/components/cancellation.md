---
id: component:cancellation
title: Cancellation
state: specified
confidence: reviewed
owner: dana
level: component
responsibility: Decide whether an order may still be cancelled, and do it.
parent: component:orders
implemented_by:
- acme#src/orders/cancel.py
relates:
- to: interface:order-events
  type: calls
  description: publishes the cancellation
  technology: JSON over the event bus
- to: quality:cancel-latency
  type: satisfies
---
