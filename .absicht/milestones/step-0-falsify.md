---
id: milestone:step-0-falsify
title: Step 0 — falsify the packet
state: unknown
confidence: assumed
owner: vfeenstr
outcome: Hand-written packets for three real slices, and a measurement of
  agent output against them
includes:
- story:hand-a-slice-to-an-agent
may_decide:
- which three slices
- how agent output is measured
unresolved:
- question:smallest-schema
- question:context-horizon
done_when:
- story:hand-a-slice-to-an-agent#ac-1
- story:hand-a-slice-to-an-agent#ac-3
---

The falsification. If a hand-written packet does not measurably improve what
an agent produces, the rest of the project is decoration and should stop
here. Needs a text editor and nothing else.
