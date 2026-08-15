# 92 — `ab mine --repo PATH` (later — not yet scoped for implementation)

## Status

**Do not assign this task until every file numbered below 90 in this folder
has landed.** See [`90-later-extract.md`](90-later-extract.md)'s Status
section — the same reasoning applies. This is also explicitly the least
decided of the four "later" commands — it's the only one of the four the
README's own Open Questions section touches directly: *"How much design
truth can be mined from git history before a human has to confirm it?"* —
unanswered as of this writing.

## Spec
> Candidate decisions from git history, PRs and ADR folders, with
> provenance and confidence, for a human to accept or kill.
>
> — [`../spec/cli.md`](../spec/cli.md#later)

## What this task will need, when it's picked up

- No flag table in the spec at all. Before any code: decide and write one,
  including — given the description explicitly says "for a human to accept
  or kill" — what the *review* interface looks like. A `--print`/`--out`
  pair that emits `Rejection`/`Decision` candidates as draft files an
  `ab new`-style workflow already knows how to write is the shape most
  consistent with the rest of this command surface (files first, no
  editor); confirm that against whatever's landed by the time this is
  picked up rather than assuming it still holds.
- `Confidence` (already modeled: `assumed`/`reviewed`/`verified`) is very
  likely the field this command's output should default to `assumed` on —
  mined, not reviewed — and the "for a human to accept or kill" framing
  means this command should almost certainly never write directly into the
  live store; it should produce candidates somewhere a human explicitly
  promotes from (a review directory, `--print` to a file the human curates
  by hand, or similar). Get that boundary right before writing extraction
  logic — the wrong default here (auto-accepting mined decisions) would
  undermine the entire "design is deliberate, not inferred" premise of the
  project.
- Depends on, at minimum: [`01-codec.md`](01-codec.md) (for whatever draft
  format candidates are written in), and PR/git-history mining will need
  more from a hosting API (GitHub PRs) than [`05-git.md`](05-git.md) as
  specced provides — that's a new, separate integration, scope it
  explicitly rather than stretching `absicht.git`'s narrow read-only local
  surface to cover it.
