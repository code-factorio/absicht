---
id: req:verify-returned-work
title: Verify what came back
state: specified
confidence: reviewed
owner: vfeenstr
statement: Returned work must be verified against the packet it was issued
  from.
priority: must
actors:
- actor:designer
- actor:ci
relates:
- to: goal:bounded-context
  type: derives_from
---

The half no generic quality gate can do: the diff touched only in-scope
components, nothing out_of_scope was built, nothing was built on an unknown
without a recorded decision covering it, every interface in scope has a
running contract test, every done_when observation has something verifying
it, scenarios unmodified against the seal. Every must and must_not
observation reports checked, no_check or advisory — absicht does not run
checks and does not own assertions.
