---
id: req:capture-notes
title: Capture thoughts at near-zero friction
state: specified
confidence: verified
owner: vfeenstr
statement: A designer must be able to capture a thought as a note with
  near-zero friction.
priority: must
actors:
- actor:designer
relates:
- to: goal:intent-survives
  type: derives_from
---

Notes are committed under .absicht/notes/, carry no classification, and are
never packet input — an agent never sees a note. The inbox surfaces age, not
just count. If it matters to the work, promotion turns it into a question,
decision, requirement or behavior.
