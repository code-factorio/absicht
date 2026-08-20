---
id: component:orders-api
title: Orders API
state: specified
confidence: reviewed
owner: kim
level: container
responsibility: Take orders and say when one settles.
technology: Python 3.14
parent: component:acme
implemented_by:
- orders#api
relates:
- to: external:payment-provider
  type: calls
  description: takes the payment
  technology: HTTPS/JSON
---
