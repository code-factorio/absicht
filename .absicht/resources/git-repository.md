---
id: resource:git-repository
title: The git repository
state: specified
confidence: verified
owner: vfeenstr
resource_kind: store
technology: git
---

The repository the store lives in and the repos implementing units live in.
ab reads it at revisions (--rev), diffs it (--diff-base, --since) and stamps
markers into it. We do not design git; we depend on what a revision means.
