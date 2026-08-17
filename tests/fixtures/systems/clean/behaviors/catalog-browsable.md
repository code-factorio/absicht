---
id: behavior:catalog-browsable
title: The catalog answers a browse
state: specified
trigger: A customer opens the catalog.
realizes:
- requirement:browse-catalog
observations:
- id: behavior:catalog-browsable#obs-1
  statement: The catalog page lists the current products
  at: component:catalog
  outcome: must
---
