---
id: requirement:model-elements
title: The model holds intent as typed elements
state: specified
confidence: verified
owner: vfeenstr
realized_by:
- component:models
constrains:
- seam:record-format
---

Components, seams, data entities, requirements, NFRs, stories, decisions,
rejections, questions, milestones, externals — and, per the addendum,
resources and behaviors with inline observations. Every element declares one
of six states (specified, constrained, delegated, unknown, observed,
out_of_scope) and may carry a free-text owner; incompleteness is a state, not
an omission. Notes are deliberately not elements.

Each state implies an agent posture — specified: implement as written, flag
contradictions; constrained: choose within the guardrails, show reasoning;
delegated: decide, record the result, raise an ADR if it matters; unknown:
ask, spike, or mark blocking, never invent; observed: do not implement, do
not remove, ask; out_of_scope: do not build, report scope leakage.
