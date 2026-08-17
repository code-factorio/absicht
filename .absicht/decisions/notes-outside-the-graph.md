---
id: decision:notes-outside-the-graph
title: Notes are outside the graph
state: specified
confidence: reviewed
owner: vfeenstr
status: accepted
decided_on: 2026-08-16
reversibility: costly
applies_to:
- component:notes
- component:load
---

## Context

The moment authoring a note asks for classification it stops being used, and
the thinking goes back to a scratch file — the outcome the note exists to
prevent. And a note an agent optimises around is a note corroding the model.

## Consequences

A note is a Record, not an Element: not in `Design`, not in the Index, no
state, referenced by nothing, never packet input. Terminal states are
promoted or dropped; promotion records `promoted_to` and clears the inbox.
Committed, so a colleague can promote.
