# 43 — `ab diff REF_A REF_B`

## Depends on
[00-conventions.md](00-conventions.md), [04-findings.md](04-findings.md)
(not for findings exactly, but for the general "structured comparison
result, rendered per `--format`" pattern — reuse the rendering conventions,
not necessarily the `Finding` type itself, since a diff entry isn't a
problem, it's a change), [05-git.md](05-git.md), [20-build.md](20-build.md).

## Spec
> What changed in the design between two revisions, as elements rather than
> lines: decisions added, seams whose contract moved, requirements added or
> dropped, state transitions.
>
> - `--scope REF` limit to a subtree
> - `--kind KIND`
> - `--format {text,json,md}`
>
> — [`../spec/cli.md`](../spec/cli.md#ab-diff-ref_a-ref_b)

## What to build

`src/absicht/diff.py`:

- Build a `Design` at `REF_A` and at `REF_B` (via
  [`05-git.md`](05-git.md) + `absicht.build`'s in-memory path — no need to
  write `design.json` to disk for either).
- `DesignDiff` (or similar): a list of typed changes —
  `Added(kind, ref)`, `Removed(kind, ref)`, `StateChanged(ref, from, to)`,
  `FieldChanged(ref, field, before, after)` (at minimum for the fields the
  spec's example calls out as interesting: a `Seam`'s `contract`, a
  `Requirement`'s presence/absence, any `Element.state`) — computed by
  comparing elements present in both by id, field by field (pydantic gives
  you `.model_dump()` on each side; a straightforward dict diff over that is
  enough, no need for a generic deep-diff dependency for a data shape this
  well-typed).
- `--scope REF`: restrict the compared element sets to a subtree (same
  `contains`-walk `--scope` uses elsewhere, e.g.
  [`26-render-site.md`](26-render-site.md) — factor this subtree-selection
  helper into `absicht.resolve` if it's now needed in three places, rather
  than writing it a third time).
- `--kind KIND`: restrict to one `Kind`'s elements.
- `--format text`/`json`/`md` (a changelog-shaped Markdown document is a
  reasonable `md` rendering — "decisions added" as one section, "state
  transitions" as another, matching the spec's own framing).

## Out of scope

- No three-way diff / merge-conflict resolution — always exactly two
  revisions.
- No line-level diff of file content — the spec is explicit this is
  element-level, not `git diff`'s output; don't fall back to shelling out
  to `git diff` and calling it done.

## Tests

- Against a throwaway git fixture (per [`05-git.md`](05-git.md)'s pattern)
  with two commits to a small store: adding a requirement between them
  shows up as `Added`, changing a seam's `contract` shows up as
  `FieldChanged`, changing an element's `state` shows up as
  `StateChanged` specifically (not a generic `FieldChanged`, since the spec
  calls state transitions out by name — worth its own change type for
  cleaner rendering).
- `--scope`/`--kind` each independently narrow the result.
- `REF_A == REF_B` (or a rev with no changes to `--scope`/`--kind`'s
  subset) produces an empty diff, not an error.

## Definition of done

- `absicht.diff` added to the import-linter layers list.
- `tests/test_cli.py`: `diff` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
