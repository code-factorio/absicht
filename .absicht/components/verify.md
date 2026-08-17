---
id: component:verify
title: verify
state: specified
confidence: verified
owner: vfeenstr
responsibility: Checks the returned change against the sealed packet — scope
  leakage, unmet criteria, modified scenarios — and reports every must and
  must_not observation as checked, no_check or advisory.
consumes:
- seam:design-artifact
- seam:findings-report
- seam:run-store
implemented_by:
- absicht#src/absicht/verify.py
---
