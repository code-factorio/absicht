---
id: data:order
title: Order
state: specified
confidence: reviewed
owner: dana
owner_component: component:orders
fields:
- name: id
  type: str
- name: state
  type: str
  note: placed, cancelled, shipped
- name: placed-at
  type: datetime
identity:
- id
---
