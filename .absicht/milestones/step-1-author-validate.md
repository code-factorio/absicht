---
id: milestone:step-1-author-validate
title: Step 1 — author and validate
state: specified
confidence: verified
owner: vfeenstr
outcome: Schema, file layout and ab check — link integrity, orphans,
  ungoverned elements
includes:
- story:author-an-element
- story:validate-a-store
scope:
- component:models
- component:codec
- component:load
- component:resolve
- component:findings
- component:git
- component:check
- component:cli
- component:init
- component:new
- component:schema
- component:migrate
must_hold:
- decision:files-first-store
- decision:pydantic-single-schema-source
- decision:layer-stack-import-contracts
done_when:
- story:validate-a-store#ac-1
- story:validate-a-store#ac-2
depends_on: []
---

Tickets pnqsrz through vwv3z7. Landed before the rest; every later step
assumes check passed.
