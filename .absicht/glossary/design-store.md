---
id: term:design-store
title: Design store
state: specified
confidence: reviewed
owner: vfeenstr
definition: >-
  The store that owns composition and implementation references. Embedded as
  the `.absicht/` directory in the repo it describes, or a repo of its own.
---

The store wins. A marker in an implementing repo is a discovery hint that
`ab check` verifies against the store.
