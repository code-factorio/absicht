---
id: question:context-horizon
title: What is the right context horizon for a packet?
state: unknown
owner: vfeenstr
question: How far beyond the selected scope must a packet reach?
method: spike
blocks:
- req:bounded-handoff
---
Selected scope at full fidelity plus one ring of neighbouring contracts is
the hypothesis, not the answer. A packet for a component consuming three
libraries and two vendors is the shape to design against.
