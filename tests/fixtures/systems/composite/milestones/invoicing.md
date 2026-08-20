---
id: milestone:invoicing
title: Invoicing
state: specified
confidence: reviewed
owner: kim
outcome: A settled order produces an invoice, in the other repository.
includes:
- behavior:order-settles
scope:
- component:orders-api
- component:billing-worker
may_decide:
- Where the invoice number comes from.
done_when:
- behavior:order-settles#obs-2
---
