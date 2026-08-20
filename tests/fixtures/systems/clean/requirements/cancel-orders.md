---
id: req:cancel-orders
title: Cancel an order
state: specified
confidence: reviewed
owner: dana
statement: A customer must be able to cancel an order that has not shipped.
rationale: A cancellation nobody can do themselves becomes a support contact.
priority: must
actors:
- actor:customer
relates:
- to: goal:cheap-orders
  type: derives_from
---
