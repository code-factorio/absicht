---
id: milestone:step-1-author-validate
title: Step 1 — author and validate
state: specified
confidence: verified
owner: vfeenstr
outcome: Schema, file layout and ab check — link integrity, orphans,
  ungoverned elements
includes:
- behavior:scaffold-minimal-element
- behavior:check-flags-broken-store
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
- behavior:check-flags-broken-store#obs-1
- behavior:check-flags-broken-store#obs-2
---
Its own tickets run pnqsrz through vwv3z7 (tasks 10-17); the foundations
wave it stands on is milestone:foundations. Landed before the rest; every
later step assumes check passed.
