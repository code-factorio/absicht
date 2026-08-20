---
id: data:element-record
title: Element record
state: specified
confidence: verified
owner: vfeenstr
owner_component: component:codec
fields:
- name: id
  type: Ref
  note: kind:slug — identity carries no location
- name: title
  type: str
- name: state
  type: State
  note: the six-valued incompleteness axis
- name: owner
  type: str?
  note: free-text handle on every element
- name: tags
  type: tuple[str, ...]
- name: body
  type: markdown
  note: follows the front matter verbatim, never parsed
identity:
- id
---

Common base of every element. source is set by the loader, never authored.
