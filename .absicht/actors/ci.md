---
id: actor:ci
title: CI runner
state: specified
confidence: reviewed
owner: vfeenstr
actor_kind: system
goals:
- Fail the build when the store contradicts itself.
- Verify returned work against the packet it was given, offline.
- Report which units are behind the design, and how far.
- Bump the watermark in the commit that lands the work.
---

`ab check` runs against absicht's own `.absicht/` in CI. If your own design
fails your own validator, that is the most informative test in the repo.
`ab verify` must run offline against a fetched packet, in CI, in somebody
else's repo.
