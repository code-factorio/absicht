# 45 — `ab marker check`

## Depends on
[44-marker-sync.md](44-marker-sync.md) (reuses its store→expected-marker
computation), [04-findings.md](04-findings.md).

## Spec
> `ab marker check --repo PATH` fail if a marker disagrees with the store
>
> The store is what an agent dropped into an implementing repo reads to
> find its design without being told where to look... The marker is a
> discovery hint, never authority. The design repo owns composition and
> implementation references; `ab check` verifies the two agree and treats
> a mismatch as an error.
>
> — [`../spec/cli.md`](../spec/cli.md#ab-marker), README's Discovery section

(The README passage says `ab check` verifies agreement; `cli.md` gives that
job its own subcommand, `ab marker check`. Trust `cli.md` — it's the surface
spec this whole task list is built from — and treat the README line as
describing the *feature*, not naming which exact command implements it. If
[`13-check-integrity.md`](13-check-integrity.md) already added a marker
cross-check by the time this lands, resolve the duplication in favor of one
implementation, called from wherever makes sense; don't ship the same
comparison logic twice.)

## What to build

Add to `src/absicht/markers.py`:

- `check(design: Design, repo: Path) -> tuple[Finding, ...]` — read the
  existing `.absicht` at `repo` (a `USAGE`-worthy problem if it's missing
  entirely, or a directory instead of a file — `marker check` on an
  embedded repo doesn't make sense, say so clearly), compute what
  [`44-marker-sync.md`](44-marker-sync.md)'s `sync()` *would* write (same
  logic, factor it so `check` calls the same expected-marker builder rather
  than a parallel implementation), and diff:
  - A unit present in the store's expectation but missing from the marker,
    or vice versa → `Finding`.
  - A unit present in both but with a different `path` → `Finding`
    (component moved and the marker wasn't resynced).
  - **Not** a mismatch: a unit's `at`/`design_rev` differing from
    "current design head" — that's drift, which is `ab status`'s entire
    subject ([`42-status.md`](42-status.md)), not a marker-correctness
    problem. `marker check` verifies the marker's *shape* (which units,
    which paths) agrees with the store, not how far behind it is.

## Out of scope

- No drift/watermark-staleness reporting — `ab status`.
- No auto-fix — `marker check` reports, `marker sync` fixes; keep the
  read/write split clean, it's the same split `ab check`/nothing-fixes-it
  and `ab build` have elsewhere in this project.

## Tests

- Against a repo whose marker was just produced by `marker sync`: `OK`,
  empty report.
- Against a repo whose marker is missing a unit the store now expects
  (simulate: sync, then add a new `implemented_by` entry to the design and
  check again without re-syncing): `FINDINGS`, names the missing unit.
- Against a repo whose marker names a unit at a stale `path`: `FINDINGS`.
- A missing `.absicht` file, and a `.absicht/` directory, at `repo`: both
  `USAGE`, distinctly worded.

## Definition of done

- `tests/test_cli.py`: `marker check` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
