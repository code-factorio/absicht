---
id: component:notes
title: notes
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: The note lifecycle around the note's exclusion from the
  graph — add, list with age, promote into a real element, drop. Capture
  friction stays near zero; classification happens at promotion.
parent: component:ab
implemented_by:
- absicht#src/absicht/notes.py
relates:
- to: req:author-store
  type: implements
- to: req:capture-notes
  type: implements
---
