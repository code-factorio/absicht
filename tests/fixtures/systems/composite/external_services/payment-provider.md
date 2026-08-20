---
id: external:payment-provider
title: Payment provider
state: delegated
confidence: verified
owner: kim
reversibility: one_way
technology: REST/JSON
contract: https://example.invalid/payments/openapi.yaml
assumptions:
- A charge settles within two hours.
- The idempotency key is honoured for 24 hours.
failure_modes:
- A settled charge is reported as pending for minutes.
verified_on: 2026-02-20
expires_on: 2099-02-20
---
Checked, and current: the counterpart to `brownfield/`'s lapsed one.
