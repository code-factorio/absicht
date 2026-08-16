---
id: behavior:order-placed
title: Order placed
state: specified
lifecycle: superseded
trigger: A customer places an order.
realizes:
- requirement:cancel-orders
observations:
- id: behavior:order-placed#obs-1
  statement: The order appears in the order cache
  at: resource:order-cache
  outcome: must
  timing: immediate
---
