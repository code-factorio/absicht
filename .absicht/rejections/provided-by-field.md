---
id: rejection:provided-by-field
title: A provided_by field on resources
state: specified
confidence: reviewed
owner: vfeenstr
applies_to:
- component:models
rejected_on: 2026-08-16
milestone: milestone:addendum-model
---

Whether we control a resource is already expressed by `state` — specified
for something we define, delegated for another team's, out_of_scope for
deliberately outside. C4 resolves the same question the same way: you do not
run S3, but you own your buckets. A second field would answer it twice.
