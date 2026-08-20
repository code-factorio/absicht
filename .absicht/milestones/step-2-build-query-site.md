---
id: milestone:step-2-build-query-site
title: Step 2 — build, query, look at it
state: specified
confidence: verified
owner: vfeenstr
outcome: ab build, the query surface and the read-only site with stable-layout
  diagrams
includes:
- behavior:show-answers-both-directions
- behavior:site-shows-every-kind
scope:
- component:build
- component:render
- component:diagram
- component:layout
must_hold:
- quality:byte-identical-build
done_when:
- behavior:show-answers-both-directions#obs-2
- behavior:diagrams-keep-their-positions#obs-2
---
Tickets jcx9dm through 1q9ymw. Read-only projections, precisely so that "do
I actually look at these" gets answered before anything is made editable.
