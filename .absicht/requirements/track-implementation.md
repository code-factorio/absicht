---
id: requirement:track-implementation
title: Track where the code stands against the design
state: specified
confidence: reviewed
owner: vfeenstr
realized_by:
- component:status
- component:diff
- component:markers
---

status computes drift from watermarks and implementation refs; diff compares
the design between revisions as elements rather than lines; marker sync,
check and stamp manage the discovery hints in implementing repos. The store
wins over every marker.
