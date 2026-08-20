---
id: req:dogfood-in-ci
title: ab check runs against absicht's own store in CI
state: unknown
owner: vfeenstr
statement: CI must run ab check against absicht's own design store.
priority: must
actors:
- actor:ci
relates:
- to: goal:intent-survives
  type: derives_from
---

Promoted from a note captured against step 1. CI's own comment says the
dogfood job arrives with step 1; the tickets say step 1 closed long ago and
the job never landed. If your own design fails your own validator, that is
the most informative test in the repo — and this store now exists to be
failed.
