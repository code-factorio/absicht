---
id: milestone:step-4-verify
title: Step 4 — verify what came back
state: specified
confidence: verified
owner: vfeenstr
outcome: ab verify, ab status, ab diff and the marker commands
includes:
- story:check-what-came-back
- story:track-drift
- story:review-a-design-change
scope:
- component:verify
- component:status
- component:diff
- component:markers
must_hold:
- decision:watermarks-are-hints
- nfr:additive-json
done_when:
- story:check-what-came-back#ac-1
- story:track-drift#ac-1
depends_on:
- milestone:step-2-build-query-site
- milestone:step-3-handoff
---

Tickets 3qzxf2 through gw958w. The half no generic quality gate can do:
whether it is the code that was asked for. extract, import, mine and serve
were dropped from scope as not-yet-falsifiable.
