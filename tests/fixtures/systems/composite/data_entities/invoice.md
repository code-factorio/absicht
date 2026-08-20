---
id: data:invoice
title: Invoice
state: specified
confidence: reviewed
owner: kim
owner_component: component:billing-worker
fields:
- name: number
  type: str
- name: order-id
  type: str
- name: amount
  type: Money
identity:
- number
---
