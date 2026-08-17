---
id: rejection:canvas-suite
title: A canvas or diagramming suite
state: specified
confidence: reviewed
owner: vfeenstr
applies_to:
- component:diagram
rejected_on: 2026-08-15
milestone: milestone:step-2-build-query-site
---

Diagrams are generated projections and navigation aids, not an authoring
surface. The moment boxes can be dragged into meaning, the diagram stops
being a faithful view of the store — which is the entire reason positions
are pinned data rather than free manipulation.
