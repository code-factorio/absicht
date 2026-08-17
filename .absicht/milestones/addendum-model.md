---
id: milestone:addendum-model
title: The model addendum
state: specified
confidence: verified
owner: vfeenstr
outcome: Resources, behaviors with observations, notes, derived scope and
  composition, lifecycle and supersession, the run store — through every
  layer
includes:
- story:capture-a-thought
scope:
- component:models
- component:load
- component:resolve
- component:check
- component:notes
- component:runstore
- component:packet
- component:verify
- component:render
- component:diagram
- component:cli
- component:new
must_hold:
- decision:resource-kind-three-values
- decision:derive-dont-store
- decision:notes-outside-the-graph
- decision:run-store-not-in-git
- decision:renderers-last
unresolved:
- question:stream-vs-store
- question:lifecycle-beyond-behaviors
- question:observation-evidence-hint
- question:brownfield-behavior-import
done_when:
- story:capture-a-thought#ac-1
- story:capture-a-thought#ac-2
depends_on:
- milestone:step-2-build-query-site
- milestone:step-3-handoff
- milestone:step-4-verify
---

Tasks 50 through 60, tickets 32qgzq through 4r5xrr. CLI before site on every
addition, per the renderers-last rule.
