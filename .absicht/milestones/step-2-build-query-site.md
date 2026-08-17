---
id: milestone:step-2-build-query-site
title: Step 2 — build, query, look at it
state: specified
confidence: verified
owner: vfeenstr
outcome: ab build, the query surface and the read-only site with stable-layout
  diagrams
includes:
- story:inspect-the-design
- story:see-the-site
scope:
- component:build
- component:render
- component:diagram
- component:layout
must_hold:
- nfr:byte-identical-build
done_when:
- story:inspect-the-design#ac-2
- story:see-the-site#ac-1
depends_on:
- milestone:step-1-author-validate
---

Tickets jcx9dm through 1q9ymw. Read-only projections, precisely so that "do
I actually look at these" gets answered before anything is made editable.
