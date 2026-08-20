---
id: behavior:catalog-browsable
title: Browsing the catalog signed out
state: specified
confidence: reviewed
owner: dana
trigger: A visitor opens the catalog without a session.
observations:
- id: behavior:catalog-browsable#obs-1
  statement: The catalog answers with the items that are for sale.
  at: component:catalog
  outcome: must
relates:
- to: req:browse-catalog
  type: realizes
---
