---
id: behavior:order-placed-v2
title: Order placed through checkout
state: specified
trigger: A customer places an order through the new checkout.
realizes:
- requirement:cancel-orders
supersedes:
- behavior:order-placed
observations:
- id: behavior:order-placed-v2#obs-1
  statement: The order appears in the order cache
  at: resource:order-cache
  outcome: must
  timing: immediate
- id: behavior:order-placed-v2#obs-2
  statement: The order shows in the customer's order list
  at: component:orders
  outcome: must
  timing: eventual
- id: behavior:order-placed-v2#obs-3
  statement: No order is cached before payment clears
  at: resource:order-cache
  outcome: must_not
- id: behavior:order-placed-v2#obs-4
  statement: The superseded order-placed behavior still fires while readers migrate
  at: behavior:order-placed
  outcome: must
  timing: eventual
- id: behavior:order-placed-v2#obs-5
  statement: The cache warms before the first read
  at: component:orders
  outcome: should
---
