---
id: data:finding
title: Finding
state: specified
confidence: verified
owner: vfeenstr
owner_component: component:findings
fields:
- name: rule
  type: str
  note: layer/rule-name, registered in RULES
- name: severity
  type: Severity
- name: element
  type: Ref?
- name: message
  type: str
identity:
- rule
- element
---
