---
id: quality:cancel-latency
title: Cancelling is immediate to a human
state: specified
confidence: reviewed
owner: dana
attribute: latency
stimulus: 1000 concurrent cancellations
measure: p99 response time
target: < 200 ms
scope:
- component:cancellation
priority: must
evidence:
- bench/cancel.py
---
