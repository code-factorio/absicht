---
id: resource:runs-db
title: The runs database
state: specified
confidence: verified
owner: vfeenstr
resource_kind: store
technology: SQLite
---

The addressable file verification evidence points at: .absicht/build/runs.db.
We design its schema (component:runstore owns it) but treat the file as an
addressable thing observations check — a row exists, a run was recorded.
