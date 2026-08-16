---
id: component:orders
title: Orders
state: specified
responsibility: Take orders and record what happened to them.
contains:
- component:catalog
provides:
- seam:order-events
owns_data:
- data:order
---
