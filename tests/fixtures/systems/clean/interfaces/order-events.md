---
id: interface:order-events
title: Order events
state: specified
confidence: reviewed
owner: dana
style: event
declared_by: component:orders
contract: docs/order-events.md
operations:
- name: order-cancelled
  signature: 'OrderCancelled { order_id: str, at: datetime }'
  idempotent: true
implemented_by:
- acme#src/orders/events.py
failure_modes:
- The bus is unreachable and the event is dropped.
---
