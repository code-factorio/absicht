---
id: external:payment-api
title: Payment API
state: delegated
confidence: assumed
owner: sam
reversibility: one_way
technology: REST/JSON
contract: https://example.invalid/payments/openapi.yaml
assumptions:
- A refund settles within one business day.
- The idempotency key is honoured for 24 hours.
failure_modes:
- A settled charge is reported as pending for minutes.
verified_on: 2024-01-15
expires_on: 2025-01-15
---
The assumptions lapsed. Nobody re-checked, which is exactly what the expiry
date exists to say out loud.
