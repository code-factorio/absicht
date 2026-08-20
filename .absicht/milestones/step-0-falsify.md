---
id: milestone:step-0-falsify
title: Step 0 — falsify the packet
state: unknown
confidence: assumed
owner: vfeenstr
outcome: Hand-written packets for three real slices, and a measurement of
  agent output against them
includes:
- behavior:packet-bounds-the-work
scope:
- component:packet
may_decide:
- which three slices
- how agent output is measured
unresolved:
- question:smallest-schema
- question:context-horizon
done_when:
- behavior:packet-bounds-the-work#obs-1
- behavior:packet-bounds-the-work#obs-4
---
The falsification. If a hand-written packet does not measurably improve what
an agent produces, the rest of the project is decoration and should stop
here. Needs a text editor and nothing else.
