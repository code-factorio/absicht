# 57 — Packet: behaviors as content — satisfy, don't-break, one hop

## Depends on
[00-conventions.md](00-conventions.md),
[50-addendum-conventions.md](50-addendum-conventions.md),
[56-derived-scope-composition.md](56-derived-scope-composition.md),
[31-packet-assembly.md](31-packet-assembly.md) and
[32-packet-cli.md](32-packet-cli.md) — **landed first**; this task extends
`absicht.packet`, it does not create it.

## Goal

The addendum's highest-value output: a packet that tells the agent not only
what to build but what it must not break. Behaviors become packet content in
two computed lists, with composition expanded exactly one hop.

## Spec

> A milestone selects which behaviors a slice must *newly satisfy*. This
> changes what a packet contains:
>
> - Behaviors this slice must **satisfy** — the new work
> - Behaviors it must **not break** — standing expectations touching the
>   components in scope
>
> The second list did not exist before this addendum and is the more
> valuable of the two. It is the mechanical form of "do not regress the rest
> of the system", which is otherwise left to an agent's judgement.
>
> — [addendum §5](../spec/ABSICHT-MODEL-ADDENDUM.md#5-lifecycle-and-supersession)

> If A composes B and B composes C, a packet scoped to A includes B's
> observations and *references* C without expanding it. Unbounded expansion
> means a packet silently grows to include half the system.
>
> — [addendum §4.2](../spec/ABSICHT-MODEL-ADDENDUM.md#42-composition)

## What to build

In `absicht.packet` (+ `Packet` in `models.py`, additive fields):

- `Packet` grows `satisfy: tuple[Ref, ...]` and
  `must_not_break: tuple[Ref, ...]`, and the behaviors themselves ride in
  `elements` at the appropriate fidelity (below).
- **Must-satisfy**: `Milestone.includes` filtered to `behavior:` refs
  (pinned in `50-addendum-conventions.md`). These enter `elements` at
  `Fidelity.FULL` — observations included; they are the work.
- **Must-not-break**: every `lifecycle: active` behavior whose `touches`
  (from 56) intersects the packet's full-fidelity scope refs, minus the
  must-satisfy set. Superseded behaviors never appear — they "stop being
  packet input" (§5). Also `FULL` — an observation you may not break is
  only actionable verbatim.
- **One-hop composition**: for each included behavior, a composed behavior
  (an observation's `at` naming `behavior:B`) joins `elements` with its
  observations (that is "includes B's observations"); behaviors *B*
  composes in turn are referenced — present as refs in B's observations —
  but not added to `elements`. Depth is measured from each included
  behavior. Guard the walk against cycles (check may not have run).
- **Notes**: cannot appear — they are not in `Design`. Assert it in a test
  anyway; the rule is important enough to pin against regression
  ("an agent never sees a note", §6).
- Rendering (`ab packet` md/json): two clearly separated sections; the
  must-not-break section leads with the addendum's framing — these are
  standing expectations, breaking one is a regression. Effective timing
  (51's helper) is rendered per observation, so the agent never computes a
  default.
- Recording packet issuance in the run store is [58](58-run-store.md)'s
  wiring; if 58 has landed, call it here (packet id + timestamp at the
  `ab packet` CLI layer, not in pure assembly — determinism).

## Out of scope

- Verification of observations — [59](59-verify-observations.md).
- Changing horizon/fidelity semantics for non-behavior kinds — 31/32 own
  those; this task only adds the behavior lists.

## Tests

- Fixture milestone selecting behavior A (which composes B, which composes
  C): packet contains A and B with observations, references C, never
  expands C. Cyclic composition fixture terminates.
- An active behavior touching an in-scope component lands in
  must-not-break; one touching only out-of-scope elements does not; a
  superseded behavior touching scope does not; a must-satisfy behavior is
  not repeated in must-not-break.
- Determinism: same design rev + milestone → byte-identical packet
  artifact (the §8 premise that regeneration replaces storage).
- Serialized packet contains no `note:` ref anywhere.

## Definition of done

- `./scripts/verify.sh` clean.
