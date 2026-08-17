---
id: behavior:check-flags-broken-store
title: Check flags a broken store
state: specified
lifecycle: active
owner: vfeenstr
trigger: A store that violates a rule is checked.
realizes:
- requirement:validate-store
observations:
- id: behavior:check-flags-broken-store#obs-1
  statement: The run exits FINDINGS when any finding is at error severity
    and zero when only advisories remain
  at: component:cli
  outcome: must
  timing: immediate
- id: behavior:check-flags-broken-store#obs-2
  statement: A finding names its rule id and the element or file it is about
  at: component:findings
  outcome: must
  timing: immediate
- id: behavior:check-flags-broken-store#obs-3
  statement: A store file is modified by running check
  at: resource:store-tree
  outcome: must_not
---
