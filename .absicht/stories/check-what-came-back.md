---
id: story:check-what-came-back
title: Check what came back
state: specified
confidence: reviewed
owner: vfeenstr
actor: designer
outcome: the change is judged against what was asked, not just well-formed
satisfies:
- requirement:verify-returned-work
acceptance:
- id: story:check-what-came-back#ac-1
  given:
  - a sealed packet
  - a change claimed to complete it
  when: the designer runs ab verify
  then:
  - every must and must_not observation reports checked or no_check
  - scope leakage and unmet criteria are findings
- id: story:check-what-came-back#ac-2
  kind: structural
  statement: scenario files modified against the sealed digest fail the run
  touches:
  - component:verify
- id: story:check-what-came-back#ac-3
  given:
  - an unchecked should observation
  when: the designer reads the report
  then:
  - it is counted as advisory visibility, never failed
---
