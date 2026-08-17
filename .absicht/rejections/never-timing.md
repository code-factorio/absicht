---
id: rejection:never-timing
title: A never timing for negation
state: specified
confidence: reviewed
owner: vfeenstr
applies_to:
- component:models
rejected_on: 2026-08-16
milestone: milestone:addendum-model
---

Early drafts conflated polarity and when, using a `never` timing to express
negation. Splitting outcome (`must` / `must_not` / `should`) from timing
(`immediate` / `eventual`) makes `must_not` say what it means — at no point —
and lets negative observations stay first-class, which is how double-writes
and leaks get caught.
