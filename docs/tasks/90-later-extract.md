# 90 — `ab extract --to URL` (later — not yet scoped for implementation)

## Status

**Do not assign this task until every file numbered below 90 in this folder
has landed and `main` is green.** The README's own status table lists this
under "later," after step 4, and step 0's premise — *"If a hand-written
packet does not measurably improve what an agent produces, the rest of this
is decoration and the project should stop there"* — applies transitively:
there is no point extracting a store into its own repo before the tooling
that makes a store worth having exists.

## Spec
> Move `.absicht/` out to a new store repo and leave a populated `.absicht`
> file behind. This is the transition a hand-migration gets wrong — the
> marker has to name the right units and paths, and carry a watermark for
> the commit that split them — which is why it is a command.
>
> — [`../spec/cli.md`](../spec/cli.md#later)

## What this task will need, when it's picked up

- `cli.md` gives this command one flag (`--to URL`) and a one-paragraph
  description — no full flag table like the numbered commands above. **The
  first half of this task is writing that table** (following the pattern of
  every other command's spec entry, and this project's own convention of
  every command supporting `--json` and exiting meaningfully), *then*
  proposing it in a PR touching `cli.md` before implementing against it —
  don't invent flags silently in code that the spec doesn't carry forward.
- It composes: init (in reference mode) at the destination, a full copy of
  the current embedded store's history-or-not (decide: does the new store
  repo get the design's git history, or start fresh with the current state?
  — this is exactly the kind of call worth an ADR, once
  `.absicht/decisions/` is a real thing to write one into), an
  `ab marker sync`-shaped write of the marker left behind, and a watermark
  for "the commit that split them" per the spec's own framing.
- Depends on, at minimum: [`10-init.md`](10-init.md) (reference mode),
  [`44-marker-sync.md`](44-marker-sync.md), [`46-marker-stamp.md`](46-marker-stamp.md),
  [`05-git.md`](05-git.md) (this one likely needs git *write* operations —
  `git mv`/history rewriting/a fresh `git init` at the destination — which
  is explicitly out of scope for `absicht.git` as specced in
  [`05-git.md`](05-git.md); this command will need its own careful,
  narrowly-scoped write path, reviewed with the same care as any
  history-rewriting tool, not a casual extension of the read-only wrapper).
