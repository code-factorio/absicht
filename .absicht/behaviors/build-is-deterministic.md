---
id: behavior:build-is-deterministic
title: Build is deterministic
state: specified
lifecycle: active
owner: vfeenstr
trigger: The same store is built twice from clean checkouts.
realizes:
- requirement:build-artifact
observations:
- id: behavior:build-is-deterministic#obs-1
  statement: The design artifact is byte-identical across the two builds
  at: component:build
  outcome: must
  timing: immediate
- id: behavior:build-is-deterministic#obs-2
  statement: Varying PYTHONHASHSEED changes the artifact bytes
  at: component:build
  outcome: must_not
- id: behavior:build-is-deterministic#obs-3
  statement: The fold consumes the resolved store, never the files directly
  at: seam:design-artifact
  outcome: must
  timing: immediate
---
