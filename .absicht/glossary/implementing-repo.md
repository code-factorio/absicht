---
id: term:implementing-repo
title: Implementing repo
state: specified
confidence: reviewed
owner: vfeenstr
definition: >-
  A repo holding code the design describes, carrying an `.absicht` file that
  says where the store is, which units this repo implements, and a watermark
  per unit.
---

The marker is a discovery hint, never authority. `ab check` verifies that the
marker and the store agree and treats a mismatch as an error. Markers can be
regenerated, and they are optional.
