---
id: decision:event-log
title: Event log over in-place updates
state: specified
status: accepted
decided_on: 2026-01-15
reversibility: costly
applies_to:
- component:orders
---

## Context

The audit trail is the product; in-place updates erase it.

## Consequences

Read models project from the log. Undoing this means a migration, so changes
land as new events.
