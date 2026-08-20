---
id: behavior:order-placed
title: Placing an order (the first cut)
state: specified
confidence: reviewed
owner: dana
lifecycle: superseded
trigger: The customer confirms a basket.
observations:
- id: behavior:order-placed#obs-1
  statement: The order is written with state placed.
  at: component:orders
  outcome: must
---
Kept because it is the record of what was expected before. It is not how the
system works any more.
