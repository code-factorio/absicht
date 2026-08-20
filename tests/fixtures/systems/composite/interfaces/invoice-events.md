---
id: interface:invoice-events
title: Invoice events
state: specified
confidence: reviewed
owner: kim
style: event
declared_by: component:orders-api
operations:
- name: order-settled
  signature: 'OrderSettled { order_id: str, amount: Money }'
  idempotent: true
implemented_by:
- orders#api/events.py
---
Declared in one repository, consumed in the other: the seam the multi-repo
commands are about.
