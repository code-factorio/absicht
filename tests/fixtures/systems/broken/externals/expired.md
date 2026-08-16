---
# An external assumption whose expires_on has passed: re-check before
# trusting. Stays expired — the date is fixed, "today" moves.
id: external:expired
title: Expired assumption
state: specified
external_kind: service
assumptions:
- the API stays idempotent under retries
verified_on: 2025-01-10
expires_on: 2026-01-10
---
