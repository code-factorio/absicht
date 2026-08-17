---
id: requirement:author-store
title: Author a store as files
state: specified
confidence: verified
owner: vfeenstr
realized_by:
- component:init
- component:new
- component:notes
constrains:
- seam:record-format
---

init scaffolds a mode, new scaffolds an element with a deterministic id,
notes capture thoughts at near-zero friction. Diffs, git merge-file and pull
request review keep the store honest when agents write to it — which is why
the authoring surface is files, not a UI.
