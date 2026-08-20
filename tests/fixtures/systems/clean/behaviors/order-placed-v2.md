---
id: behavior:order-placed-v2
title: Placing an order
state: specified
confidence: reviewed
owner: dana
supersedes:
- behavior:order-placed
trigger: The customer confirms a basket.
observations:
- id: behavior:order-placed-v2#obs-1
  statement: The order is written before the payment is attempted.
  at: behavior:order-placed
  outcome: must
- id: behavior:order-placed-v2#obs-2
  statement: An OrderPlaced event is emitted once the payment settles.
  at: resource:order-stream
  outcome: must
---
