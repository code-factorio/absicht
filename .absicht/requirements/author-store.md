---
id: req:author-store
title: Author a store as files
state: specified
confidence: verified
owner: vfeenstr
statement: A designer must be able to author every element of the store as a
  file on disk.
rationale: Diffs, git merge-file and pull request review keep the store honest
  when agents write to it — which is why the authoring surface is files, not a
  UI.
priority: must
actors:
- actor:designer
- actor:agent
relates:
- to: goal:intent-survives
  type: derives_from
---

init scaffolds a mode, new scaffolds an element with a deterministic id,
notes capture thoughts at near-zero friction.
