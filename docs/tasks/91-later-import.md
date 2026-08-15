# 91 — `ab import --repo PATH` (later — not yet scoped for implementation)

## Status

**Do not assign this task until every file numbered below 90 in this folder
has landed.** See [`90-later-extract.md`](90-later-extract.md)'s Status
section — the same reasoning applies.

## Spec
> Brownfield extraction: structure from code, everything intent-shaped
> lands as `observed` or `unknown`.
>
> — [`../spec/cli.md`](../spec/cli.md#later)

## What this task will need, when it's picked up

- Same situation as `extract`: one line in the spec, no flag table. Write
  the flag table (what does "structure from code" mean concretely —
  language/framework detection? directory-to-component heuristics? is
  there a `--language`/`--lang-plugin` flag, or is this v1 scoped to one
  ecosystem?) and get it reviewed before implementing against it.
- This is squarely the kind of feature `CONTEXT.md`'s "Dogfooding" section
  flags as needing a *real*, messy second codebase to be tested honestly
  against — *"absicht's own store will be pristine... Vermittlung is the
  better second victim."* Don't build this against `absicht`'s own,
  by-construction-clean repo and call it validated.
- Depends on, at minimum: [`06-fixtures.md`](06-fixtures.md)'s
  `brownfield/` fixture as the target *shape* of output (an import run
  should produce something that looks like that fixture: mostly
  `observed`, honest about gaps), [`01-codec.md`](01-codec.md)/
  [`10-init.md`](10-init.md) for writing the resulting store.
- The README is explicit that this is not a backfill project — *"the model
  fills in along the path of actual work, not through a backfill project
  that never finishes"* — so whatever heuristics this command uses should
  aim for a reasonable, honest first cut (a real reading of the code
  labeled with an honest state), not an attempt at completeness.
