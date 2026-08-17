---
id: milestone:step-3-handoff
title: Step 3 — hand work to an agent
state: specified
confidence: verified
owner: vfeenstr
outcome: ab packet and ab features — the bounded brief, sealed for offline
  verification
includes:
- story:hand-a-slice-to-an-agent
scope:
- component:gherkin
- component:packet
- component:runstore
must_hold:
- nfr:offline-operation
unresolved:
- question:one-hop-expansion
done_when:
- story:hand-a-slice-to-an-agent#ac-1
- story:hand-a-slice-to-an-agent#ac-2
depends_on:
- milestone:step-1-author-validate
---

Tickets q1efc0 through gpeky6. The packet is deterministic from milestone
plus design rev and is regenerated rather than stored.
