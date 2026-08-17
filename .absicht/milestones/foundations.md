---
id: milestone:foundations
title: The foundations wave
state: specified
confidence: verified
owner: vfeenstr
outcome: The layer stack's bottom, before any command existed — codec, load,
  resolve, findings, git and the fixture systems
scope:
- component:models
- component:codec
- component:load
- component:resolve
- component:findings
- component:git
must_hold:
- decision:layer-stack-import-contracts
depends_on: []
---

Tasks 00 through 06, tickets jfg0qy, 9zf3xj, an2ncs, m1npgk, b43rng and
pfkxrx. models.py itself predates the ticket system — the tasks README's
own snapshot says "models done, CLI scaffolded, nothing behind it yet" —
so this milestone claims the modules, not their birth commits. The four
fixture systems under tests/fixtures/systems/ are the block's other
deliverable and the repo's main safety net since.
