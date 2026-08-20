---
id: interface:findings-report
title: Findings and the report shape
state: specified
confidence: verified
owner: vfeenstr
style: call
declared_by: component:findings
implemented_by:
- absicht#tests/test_findings.py
---

One shared severity scale, Finding/Report shape and text/json/sarif rendering
for both check and verify, so a CI pipeline treats their output alike.
--strict promotes warnings for the exit-code decision only, never the
finding's own severity field.
