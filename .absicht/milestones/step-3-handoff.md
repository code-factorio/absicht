---
id: milestone:step-3-handoff
title: Step 3 — hand work to an agent
state: specified
confidence: verified
owner: vfeenstr
outcome: ab packet and ab features — the bounded brief, sealed for offline
  verification
includes:
- behavior:packet-bounds-the-work
scope:
- component:gherkin
- component:packet
must_hold:
- quality:offline-operation
unresolved:
- question:one-hop-expansion
done_when:
- behavior:packet-bounds-the-work#obs-1
- behavior:packet-carries-must-not-break#obs-1
---
Tickets q1efc0 through gpeky6. The packet is deterministic from milestone
plus design rev and is regenerated rather than stored.
