---
id: component:findings
title: findings
state: specified
confidence: verified
owner: vfeenstr
responsibility: Represents, filters and renders findings; never produces
  them. Check and verify register their rule ids here and share the
  text/json/sarif rendering.
provides:
- seam:findings-report
owns_data:
- data:finding
implemented_by:
- absicht#src/absicht/findings.py
---
