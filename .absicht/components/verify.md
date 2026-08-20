---
id: component:verify
title: verify
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Checks the returned change against the sealed packet — scope
  leakage, unmet observations, modified scenarios — and reports every must and
  must_not observation as checked, no_check or advisory.
parent: component:ab
implemented_by:
- absicht#src/absicht/verify.py
relates:
- to: req:verify-returned-work
  type: implements
- to: interface:design-artifact
  type: calls
- to: interface:findings-report
  type: calls
- to: interface:run-store
  type: calls
---
