---
id: milestone:reconcile-mvp
title: Reconciliation, first cut
state: constrained
confidence: assumed
owner: sam
reversibility: cheap
outcome: Mismatches are found the morning after, not at close of month.
includes:
- behavior:reconciliation-fires
scope:
- component:legacy-billing
may_decide:
- How the mismatch report is delivered.
unresolved:
- question:refund-window
done_when:
- behavior:reconciliation-fires#obs-2
---
