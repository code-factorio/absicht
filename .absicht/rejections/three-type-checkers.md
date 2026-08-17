---
id: rejection:three-type-checkers
title: Three type checkers in the gate
state: specified
confidence: reviewed
owner: vfeenstr
rejected_on: 2026-08-15
milestone: milestone:step-1-author-validate
---

The marginal catch rate of the third checker is tiny and you pay for it on
every push, plus three sets of ignore comments and three configs that drift.
One type checker gates — mypy strict; pyright is what the editor runs.
