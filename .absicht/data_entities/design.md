---
id: data:design
title: Design artifact
state: specified
confidence: verified
owner: vfeenstr
owner_component: component:build
fields:
- name: format-version
  type: int
- name: id
  type: Ref
- name: title
  type: str
- name: version
  type: str
- name: purpose
  type: str
- name: scope
  type: tuple[str, ...]
- name: out-of-scope
  type: tuple[str, ...]
- name: exports
  type: tuple[Ref, ...]
- name: revisions
  type: tuple[Revision, ...]
- name: imports
  type: tuple[Import, ...]
- name: repositories
  type: tuple[Repository, ...]
- name: glossary
  type: tuple[Term, ...]
- name: actors
  type: tuple[Actor, ...]
- name: goals
  type: tuple[Goal, ...]
- name: requirements
  type: tuple[Requirement, ...]
- name: qualities
  type: tuple[QualityRequirement, ...]
- name: constraints
  type: tuple[Constraint, ...]
- name: behaviors
  type: tuple[Behavior, ...]
- name: components
  type: tuple[Component, ...]
- name: interfaces
  type: tuple[Interface, ...]
- name: data-entities
  type: tuple[DataEntity, ...]
- name: resources
  type: tuple[Resource, ...]
- name: libraries
  type: tuple[Library, ...]
- name: external-services
  type: tuple[ExternalService, ...]
- name: assumptions
  type: tuple[Assumption, ...]
- name: decisions
  type: tuple[Decision, ...]
- name: questions
  type: tuple[Question, ...]
- name: rejections
  type: tuple[Rejection, ...]
- name: milestones
  type: tuple[Milestone, ...]
- name: relationships
  type: tuple[Relationship, ...]
- name: notes
  type: tuple[Note, ...]
---

Field names carry dashes where the model spells underscores — the store's
Slug pattern forbids underscores, a constraint ab's own data shapes hit.

Every collection a tuple in id order, the dump's field order the model's own:
byte-identical output needs that order to be data, not dict insertion order.
