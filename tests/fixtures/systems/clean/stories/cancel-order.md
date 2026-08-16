---
id: story:cancel-order
title: Cancel an order
state: specified
actor: customer
outcome: the order is cancelled and the refund starts
satisfies:
- requirement:cancel-orders
acceptance:
- id: story:cancel-order#ac-1
  when: the customer cancels a refundable order
  then:
  - the order is cancelled
  - the refund starts
- id: story:cancel-order#ac-2
  given:
  - an order that has already shipped
  when: the customer asks to cancel it
  then:
  - cancellation is refused
- id: story:cancel-order#ac-3
  kind: structural
  statement: cancellation only consumes the order-events seam
  touches:
  - seam:order-events
---

A customer may cancel while the order can still be refunded.
