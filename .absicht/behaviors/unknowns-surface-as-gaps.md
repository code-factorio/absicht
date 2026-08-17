---
id: behavior:unknowns-surface-as-gaps
title: Unknowns surface as gaps
state: specified
lifecycle: active
owner: vfeenstr
trigger: The unfinished worklist is requested.
realizes:
- requirement:query-design
observations:
- id: behavior:unknowns-surface-as-gaps#obs-1
  statement: Every unknown, observed and delegated element appears, with open
    questions, unowned elements, expired assumptions and observation-less
    behaviors
  at: component:render
  outcome: must
  timing: immediate
- id: behavior:unknowns-surface-as-gaps#obs-2
  statement: An unowned unknown with one referencing owner reports that owner
    as inherited
  at: component:render
  outcome: must
  timing: immediate
---
