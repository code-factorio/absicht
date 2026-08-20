---
id: behavior:notes-never-reach-agents
title: Notes never reach agents
state: specified
lifecycle: active
owner: vfeenstr
trigger: A note is captured against the store.
observations:
- id: behavior:notes-never-reach-agents#obs-1
  statement: The note is committed under .absicht/notes/
  at: resource:store-tree
  outcome: must
  timing: immediate
- id: behavior:notes-never-reach-agents#obs-2
  statement: A note appears in the build artifact
  at: component:build
  outcome: must_not
- id: behavior:notes-never-reach-agents#obs-3
  statement: Promotion records promoted_to and removes the inbox line
  at: component:notes
  outcome: must
  timing: immediate
- id: behavior:notes-never-reach-agents#obs-4
  statement: The note lists in the inbox with its age
  at: component:notes
  outcome: must
  timing: immediate
relates:
- to: req:capture-notes
  type: realizes
---
