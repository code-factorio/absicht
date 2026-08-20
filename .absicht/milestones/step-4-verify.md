---
id: milestone:step-4-verify
title: Step 4 — verify what came back
state: specified
confidence: verified
owner: vfeenstr
outcome: ab verify, ab status, ab diff and the marker commands
includes:
- behavior:verify-reports-unchecked-observations
- behavior:store-discovery-via-marker
- behavior:diff-speaks-in-elements
scope:
- component:verify
- component:status
- component:diff
- component:markers
must_hold:
- decision:watermarks-are-hints
- quality:additive-json
done_when:
- behavior:verify-reports-unchecked-observations#obs-1
- behavior:store-discovery-via-marker#obs-2
---
Tickets 3qzxf2 through gw958w. The half no generic quality gate can do:
whether it is the code that was asked for. extract, import, mine and serve
were dropped from scope as not-yet-falsifiable.
