---
id: decision:trace-answers-are-bounded
title: Trace answers are bounded, and say so
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: The trace walk enumerated every simple path in both directions, and on a
  dense store that set is exponential — absicht's own 121-element store holds
  more than five million paths from a single requirement, and the site's
  traceability page rendered the machine it ran on unusable before finishing a
  single page.
choice: The trace walk carries a budget of materialized paths, spent in
  deterministic walk order, and every surface says when the budget ran out.
consequences:
- The budget is 1000 paths, so the capped answer is a prefix of the uncapped one.
- A `truncated` flag is spelled wherever the paths are — text, json, the site
  page — the same discipline as `cycle_hit`, because a cut-short answer that
  reads as complete is worse than a small one that admits its size.
- 'The site page asks for fifty per requirement: an overview a person reads, not
  an export.'
- No CLI flag raises the budget; a bigger one is a reconsidered decision, not a
  tune-up.
alternatives:
- Enumerating every simple path, which is exponential on a dense store.
- A CLI flag that raises the budget, which turns a decision into a tune-up.
applies_to:
- component:render
decided_on: 2026-08-17
---

## Context

The trace walk enumerated every simple path in both directions. On a dense
store that set is exponential: absicht's own 121-element store holds more
than five million paths from a single requirement, and the site's
traceability page — one trace per requirement — rendered the machine it ran
on unusable before finishing a single page.

## Consequences

The walk carries a budget of materialized paths (1000), spent in
deterministic walk order, so the capped answer is a prefix of the uncapped
one. A `truncated` flag is spelled wherever the paths are — text, json, the
site page — the same discipline as `cycle_hit`, because a cut-short answer
that reads as complete is worse than a small one that admits its size. The
site page asks for fifty per requirement: an overview a person reads, not an
export. No CLI flag raises the budget; a bigger one is a reconsidered
decision, not a tune-up.
