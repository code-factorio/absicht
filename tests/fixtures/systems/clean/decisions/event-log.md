---
id: decision:event-log
title: Orders publish an event log
state: specified
confidence: reviewed
owner: dana
reversibility: costly
context: Cancellation and the catalog both need to know an order moved.
choice: Orders publishes every state change as an event; nobody reads its tables.
consequences:
- A reader can be added without touching Orders.
- Every reader has to cope with an event arriving twice.
alternatives:
- A shared table, which makes every reader a writer's problem.
applies_to:
- component:orders
decided_on: 2026-01-04
---
