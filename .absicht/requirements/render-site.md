---
id: req:render-site
title: Render a read-only site with stable layout
state: specified
confidence: reviewed
owner: vfeenstr
statement: The tool must render the design as a read-only site whose layout is
  the same on every build.
priority: must
actors:
- actor:designer
relates:
- to: goal:design-is-queryable
  type: derives_from
---

Element pages, traceability, gaps, the note inbox, and diagrams as
projections — svg, mermaid or d2. Positions live in layout.yaml as design
data and render never invents its own, so the same element sits at the same
place on every build and spatial memory forms.
