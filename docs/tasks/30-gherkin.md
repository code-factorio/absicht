# 30 — `absicht.gherkin`

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md).

## Goal

Behavioural `Criterion`s (`kind == CriterionKind.BEHAVIOURAL`, with `given`/
`when`/`then`) render to Gherkin `.feature` files. Shared by
[`32-packet-cli.md`](32-packet-cli.md)'s `--features` flag and
[`33-features.md`](33-features.md), which is otherwise the same rendering
with a thinner CLI around it — build it once here so neither reimplements
Gherkin syntax.

## Spec
> Render behavioural criteria to Gherkin without the rest of the packet.
> Output is generated, never authored: an agent implements step definitions
> and may not touch these files.
>
> — [`../spec/cli.md`](../spec/cli.md#ab-features-milestone)

## What to build

`src/absicht/gherkin.py`:

- `render_feature(story: Story, criteria: tuple[Criterion, ...]) -> str` —
  one `.feature` file per story: `Feature: <story.title>` (or
  `story.outcome`, whichever reads better as a Gherkin feature line — the
  `actor`/`outcome` fields on `Story` map naturally onto Gherkin's
  `As a/I want/So that` framing, consider using them), one `Scenario:`
  block per behavioural criterion, `Given`/`When`/`Then` lines from the
  criterion's own fields. Non-behavioural criteria (`structural`,
  `measured`) are skipped here — they're `ab verify`'s concern
  ([`41-verify-rules.md`](41-verify-rules.md)), not Gherkin's.
- Deterministic output: stable scenario order (criterion id order, which is
  already sequential per story — `#ac-1`, `#ac-2`, ...), stable formatting.
  This matters twice over: `ab features --check` needs to compare against
  committed files, and `ab packet --seal`'s scenario digest
  ([`32-packet-cli.md`](32-packet-cli.md)) needs the same bytes every time
  or the seal is meaningless.
- `scenario_digest(features: dict[str, str]) -> str` — a stable hash (e.g.
  `hashlib.sha256` over the sorted-by-filename concatenation, or a per-file
  digest folded into one) of the rendered `.feature` file contents,
  filename included in what's hashed so a rename counts as a change. This is
  what `packet.lock`'s `scenarios_digest` field
  (`models.py`'s `Packet.scenarios_digest`) stores, and what `ab verify`
  checks scenario files haven't drifted from.
- Which milestone's criteria to render is the *caller's* job (walking
  `Milestone.includes` → `Story.acceptance`, or `Milestone.done_when`
  directly since that's already a `tuple[CriterionId, ...]`) — this module
  takes a resolved set of stories/criteria, it doesn't know about
  milestones.

## Out of scope

- No step-definition generation — the spec is explicit that an agent writes
  those, and that this module's output must never be hand-edited (which is
  also why `--check`, in both consuming commands, exists: to catch drift).
- No Gherkin *parsing* — this is render-only, one direction.

## Tests

- A `Story` with 2 behavioural + 1 structural criterion renders a
  `.feature` file containing exactly 2 scenarios.
- Output is byte-identical across two calls with the same input.
- `scenario_digest` changes when a `then` line changes and stays the same
  when nothing does; changes when a file is renamed even if content is
  identical (confirm filename is part of the hash input, test it directly).
- Snapshot the rendered `.feature` output for a `tests/fixtures/systems/
  clean/` story via `syrupy`, so a future formatting change is caught as an
  intentional snapshot update, not a silent drift.

## Definition of done

- No new import-linter layer entry needed if this lands as part of
  `absicht.packet`'s module — but if it's its own file, add
  `absicht.gherkin` to the layers list, positioned the same place
  `absicht.packet` sits (both read a resolved `Design`, neither is read by
  anything below `packet`/`verify`).
- `./scripts/verify.sh` clean.
