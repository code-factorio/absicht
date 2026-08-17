---
id: nfr:additive-json
title: --json output is versioned and additive
state: specified
confidence: reviewed
owner: vfeenstr
attribute: operability
scope:
- component:cli
stimulus: a field's meaning has to change
measure: breaking vs additive changes across releases
target: fields are deprecated and new ones appear; meaning never changes
---

Agents parse the envelope, so a silent semantic change breaks consumers that
cannot adapt. schema_version travels in every artifact and every packet.
