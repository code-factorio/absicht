# 93 — `ab serve` (later — not yet scoped for implementation)

## Status

**Do not assign this task until every file numbered below 90 in this folder
has landed.** See [`90-later-extract.md`](90-later-extract.md)'s Status
section — the same reasoning applies, doubly so here: the spec's own entry
for this command is *"the webapp, once there is something worth looking
at"* — a condition, not a start date. README's "Not this" section is also
directly relevant: *"No canvas or diagramming suite... No editor before
step 4, and possibly never beyond dragging boxes... Not a product looking
for a market."*

## Spec
> The webapp, once there is something worth looking at.
>
> — [`../spec/cli.md`](../spec/cli.md#later)

## What this task will need, when it's picked up

- This is not a small extension of [`26-render-site.md`](26-render-site.md)'s
  `--serve` flag (a static-site local preview with polling rebuild) — that
  already exists and covers "look at the read-only site locally." `ab
  serve` implies something with more capability (write access? multi-user?
  live editing per README's "possibly never" editor caveat?) — the actual
  scope is genuinely open per `CONTEXT.md`'s "Deliberately not decided"
  section (*"Files-first or server-first once several systems and several
  people are involved... The library does not care whether records came
  from files or from Postgres, which is the point — the question stays
  open"*).
- Before writing a line of code for this: re-read `CONTEXT.md`'s open
  questions in full and confirm with whoever owns the project which of
  them have since been answered — this command's shape depends entirely on
  those answers, and guessing at them here would be building the wrong
  thing confidently.
- No dependency list given — there isn't enough of a spec yet to name one
  honestly beyond "everything else in this project, since it's the
  surface that exposes all of it."
