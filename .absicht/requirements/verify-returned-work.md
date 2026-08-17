---
id: requirement:verify-returned-work
title: Verify what came back
state: specified
confidence: reviewed
owner: vfeenstr
realized_by:
- component:verify
- component:runstore
---

The half no generic quality gate can do: the diff touched only in-scope
components, nothing out_of_scope was built, nothing was built on an unknown without a recorded decision covering it,
every seam in scope has a running contract test, every done_when criterion
has something verifying it, scenarios unmodified against the seal. Every must
and must_not observation reports checked, no_check or advisory — absicht
does not run checks and does not own assertions.
