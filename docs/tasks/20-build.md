# 20 — `ab build`

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md),
[05-git.md](05-git.md) (for `--rev`).

## Spec
> Fold the store into one normalized JSON document. Deterministic — same
> input, byte-identical output. Everything downstream reads this and
> nothing else.
>
> - `--out PATH` default `.absicht/build/design.json`
> - `--stdout`
> - `--check` build and diff against the existing artifact; non-zero if it
>   moved
>
> — [`../spec/cli.md`](../spec/cli.md#ab-build)

## What to build

`src/absicht/build.py`:

- `build(store: Path, *, rev: str | None) -> Design` — `load_store` (through
  the git-backed reader when `rev` is given, per the seam
  [`02-load.md`](02-load.md) leaves for [`05-git.md`](05-git.md)) →
  `resolve`. If load produced any `LoadError`s, this is not a silent partial
  build — the spec's determinism promise only means something for a store
  that's actually valid. Fail (`ExitCode.FINDINGS`, listing the errors,
  pointing at `ab check`) rather than emitting a `design.json` built from
  whatever parsed.
- **Determinism** is the load-bearing property here — `verification.md`
  ranks it second only to golden fixtures. Concretely: `Design` is a
  `pydantic` model; serialize via `model_dump_json()` with a fixed,
  documented key order (pydantic preserves field declaration order by
  default — confirm, don't assume, and pin it with a test) and no
  wall-clock/random content anywhere in the pipeline (there shouldn't be
  any — `Element` has no timestamp field — but this is the property to
  double-check specifically, since it's invisible until CI varies
  `PYTHONHASHSEED` and something breaks). Tuple fields, not sets or dicts
  keyed by insertion order from a filesystem walk that isn't itself sorted
  — confirm [`02-load.md`](02-load.md) sorts.
- `--stdout`: print the JSON, don't write `--out`.
- Default: write to `--out` (parent directories created as needed).
- `--check`: build in memory, compare byte-for-byte against the file at
  `--out` (or the default path) if it exists; `ExitCode.FINDINGS` and a
  diff-shaped message if they differ, `OK` if identical, `ExitCode.FINDINGS`
  too (or `USAGE`? — the spec says "non-zero if it moved," and a *missing*
  artifact has trivially "moved" from nothing — decide and test it) if no
  prior artifact exists to compare against.

## Out of scope

- No rendering, no packet assembly — `build`'s only output is `design.json`.
- No caching/incremental rebuild — a store this size doesn't need it, and
  premature caching is exactly the kind of thing `CLAUDE.md`'s YAGNI note
  warns against.

## Tests

- Byte-identical output across two runs, same input, in-process — the
  cheapest version of the determinism check; the harder version (across a
  clean checkout, varied `PYTHONHASHSEED`) belongs in CI per
  `verification.md`, not this task, but nothing here should make that CI
  job impossible to add later.
- Build over each `06-fixtures.md` system produces the expected element
  counts (a `syrupy` snapshot of the JSON per fixture is the natural test
  here — this may be the first task in the repo to actually create
  `__snapshots__/`, which `06-fixtures.md` anticipated).
- A store with a `LoadError` present fails the build with a message, doesn't
  write a partial `design.json`.
- `--check` against a stale committed artifact reports `FINDINGS`; against
  a fresh one, `OK`.

## Definition of done

- `absicht.build` added to the import-linter layers list.
- `tests/test_cli.py`: `build` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
