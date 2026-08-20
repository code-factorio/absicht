---
id: decision:notes-outside-the-graph
title: Notes are outside the graph
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: The moment authoring a note asks for classification it stops being used
  and the thinking goes back to a scratch file, and a note an agent optimises
  around is a note corroding the model.
choice: A note is a Record and not an Element, so it stays outside the design
  graph entirely.
consequences:
- A note is not in `Design`, not in the Index, has no state, is referenced by
  nothing and is never packet input.
- Its terminal states are promoted or dropped; promotion records `promoted_to`
  and clears the inbox.
- Notes are committed, so a colleague can promote one.
alternatives:
- A note as a first-class element, which asks for the classification that stops
  notes being written at all.
applies_to:
- component:notes
- component:load
decided_on: 2026-08-16
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
