---
id: decision:identity-carries-no-location
title: Identity carries no location
state: specified
confidence: reviewed
owner: vfeenstr
reversibility: costly
context: Components get extracted from monoliths into libraries into services,
  and an identity tied to a path, a repo or a deployment breaks on the first
  such move, taking everything that points at the element with it.
choice: An id is `kind:slug` and nothing else, so identity carries no location.
consequences:
- A ref is checkable without a lookup, because the prefix names the kind.
- Moving or extracting an element never breaks a link.
- Location — repo, path, deployment — lives in `implemented_by` and markers,
  which are hints, never identity.
alternatives:
- An identity tied to a path, a repo or a deployment, which breaks on the first
  extraction.
applies_to:
- component:models
decided_on: 2026-08-15
---

## Context

Components get extracted from monoliths into libraries into services. An
identity tied to a path, a repo or a deployment breaks on the first such
move, and everything pointing at the element breaks with it.

## Consequences

Ids are `kind:slug` and nothing else. A ref is checkable without a lookup
(the prefix names the kind), and moving or extracting an element never
breaks a link. Location — repo, path, deployment — lives in
`implemented_by` and markers, which are hints, never identity.
