---
id: term:watermark
title: Watermark
state: specified
confidence: reviewed
owner: vfeenstr
definition: >-
  `at` and `design_rev` in a repo's `.absicht` marker. Where the code caught
  up to, not what the code conforms to.
---

A watermark is a hint about where to look, not proof of conformance. Merged
code is not correct code. `at: M003` means someone shipped something claiming
to be M003, and nothing more. It records where the code caught up to, so drift
becomes the signal rather than the failure.
