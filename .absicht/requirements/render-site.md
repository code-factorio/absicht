---
id: requirement:render-site
title: Render a read-only site with stable layout
state: specified
confidence: reviewed
owner: vfeenstr
realized_by:
- component:render
- component:diagram
- component:layout
---

Element pages, traceability, gaps, the note inbox, and diagrams as
projections — svg, mermaid or d2. Positions live in layout.yaml as design
data and render never invents its own, so the same element sits at the same
place on every build and spatial memory forms.
