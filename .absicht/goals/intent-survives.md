---
id: goal:intent-survives
title: Intent survives the next person and the next agent
state: specified
confidence: reviewed
owner: vfeenstr
outcome: >-
  Why the system is shaped this way is still readable after the person and the
  agent who knew it are gone.
measure: findings `ab check` reports on absicht's own store in CI
target: no errors
stakeholders:
- actor:designer
- actor:agent
- actor:ci
---

A working system's design currently lives across Markdown scattered in repos,
diagrams in a browser tab, ADR folders nobody re-reads, tickets, slide decks
and a dozen dead LLM chats. None of it survives contact with the next person
or the next agent. Structure is derivable from code. Intent is not.
