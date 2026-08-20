---
id: question:one-hop-expansion
title: Does the one-hop packet expansion limit hold?
state: unknown
owner: vfeenstr
question: Is one hop of neighbouring context enough for a packet?
method: measure
blocks:
- req:bounded-handoff
---
It is a guess. Real chains will say whether one hop is too shallow; unbounded
expansion means a packet silently grows to include half the system.
