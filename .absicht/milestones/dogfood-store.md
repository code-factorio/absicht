---
id: milestone:dogfood-store
title: Dogfood the store
state: constrained
owner: vfeenstr
outcome: absicht's own design truth lives in .absicht/ and every ab command
  reads a store that describes absicht
must_hold:
- decision:trace-answers-are-bounded
includes:
- story:represent-the-design
scope:
- component:render
may_decide:
- element granularity — module-per-component vs layer-per-component
- which facts earn a prose body and which stay pure fields
done_when:
- story:represent-the-design#ac-1
- story:represent-the-design#ac-3
---

The bootstrap milestone. The store describes the system that builds the
store, so the seed was thin on purpose — and the packet could not be issued
from it: with no components in existence there was no scope to name, and
ab packet refuses a milestone that names none. The packet below was issued
once the elements existed. The scope is honest, not retrofitted: dogfooding
this store found the trace walk's exponential enumeration and the fix landed
in component:render inside this slice.
