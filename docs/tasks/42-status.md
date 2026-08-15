# 42 — `ab status`

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md),
[05-git.md](05-git.md), [20-build.md](20-build.md),
[44-marker-sync.md](44-marker-sync.md) (reads the `Marker`/`UnitWatermark`
shape it produces).

## Spec
> Reports units behind design head, which decisions and seam changes landed
> since each watermark, seams whose consumers have not caught up,
> components with no implementation reference, and milestones with unmet
> `done_when`.
>
> That is the reference-mode report. Embedded, design and code land in the
> same commit and nothing can be behind, so what is left is implementation
> coverage and unmet `done_when`.
>
> - `--repo PATH` `--unit REF` `--behind-only` `--since REF`
> - `--fail-on-drift` non-zero when anything is behind. For CI
> - `--format {text,json}`
>
> — [`../spec/cli.md`](../spec/cli.md#ab-status)

## What to build

`src/absicht/status.py`:

- **Mode detection**: does *this* store (the one `--store`/the global
  options point at) sit in embedded or reference mode? Reuse whatever
  [`02-load.md`](02-load.md) already determined resolving `--store` — don't
  re-derive the directory-vs-file `stat()` check a second time.
- **Reference mode**: for each `--repo PATH` (or every repo named in a
  marker found under the store's known implementing repos, if the design
  store tracks that list somewhere — check whether `System.units` already
  gives enough to enumerate repos without `--repo` being required; if not,
  `--repo` is effectively required in reference mode and that's fine, say
  so):
  - Read the repo's `.absicht` marker.
  - For each `UnitWatermark`: compare `design_rev` against current design
    head (or `--since REF` instead of "current head," when given). Walk
    design-repo commits between the two (via
    [`05-git.md`](05-git.md)) for `Decision`/`Seam` changes touching that
    unit's components — "which decisions and seam changes landed since
    the watermark" is asking for a `git log`-driven diff of the *design
    store itself*, not a structural `Design`-vs-`Design` diff; if that
    turns out to need the same machinery as [`43-diff.md`](43-diff.md), share
    it rather than reimplementing.
  - Seams whose `provider`'s unit has moved past a `consumer`'s unit's
    watermark — a consumer watermark older than a contract change on a
    seam it consumes.
  - `--unit REF`: restrict to one unit.
  - `--behind-only`: drop units with nothing to report.
- **Embedded mode**: no watermark concept at all (nothing to be behind).
  Report instead: components with empty `implemented_by`, milestones whose
  `done_when` criteria have no corresponding passing evidence (this overlaps
  with `ab verify`'s `done-when` rule — here it's a store-wide summary
  without a sealed packet in hand, so it's necessarily weaker: "does
  anything claim to verify this criterion" rather than "did verification
  actually pass," and that distinction is worth stating in the command's
  own output, not glossed over).
- `--fail-on-drift`: `ExitCode.FINDINGS` if reference-mode drift was found
  (meaningless/no-op in embedded mode — say so rather than silently
  ignoring the flag).
- `--format text`/`json`.

## Out of scope

- No auto-remediation, no suggesting which decisions to review — this is a
  report, matching every other read-only command in this project.

## Tests

- Against `tests/fixtures/systems/composite/`'s multi-repo shape (built for
  exactly this in [`06-fixtures.md`](06-fixtures.md)): a unit with a stale
  watermark reports the decisions/seam changes that landed since, a unit
  with a current watermark reports clean.
- Embedded-mode run against `clean/`: reports implementation coverage
  (some components lacking `implemented_by`, if the fixture has any — extend
  the fixture if it doesn't already exercise this) and unmet `done_when`,
  never mentions watermarks.
- `--fail-on-drift` flips the exit code exactly when drift exists;
  `--behind-only` drops clean units from the report.

## Definition of done

- `absicht.status` added to the import-linter layers list.
- `tests/test_cli.py`: `status` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
