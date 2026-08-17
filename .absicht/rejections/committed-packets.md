---
id: rejection:committed-packets
title: Committing packets and verification runs
state: specified
confidence: reviewed
owner: vfeenstr
applies_to:
- component:runstore
rejected_on: 2026-08-16
milestone: milestone:addendum-model
---

They are generated per run, appended rather than authored, and never
reviewed as a diff. Committing them adds volume proportional to agent
activity for no benefit. Exported packet YAML handed to an agent is an
artifact and belongs in CI artifacts if anywhere.
