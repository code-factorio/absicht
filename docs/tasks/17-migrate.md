# 17 — `ab migrate`

## Depends on
[00-conventions.md](00-conventions.md), [02-load.md](02-load.md).

## Spec
> - `--to N` default: latest
> - `--dry-run`
>
> — [`../spec/cli.md`](../spec/cli.md#ab-migrate)

## Context

`SCHEMA_VERSION = 1` in `models.py`, and it's the only version that has ever
existed. There is nothing to migrate *from* yet. Per this project's own
`CLAUDE.md`/`AGENTS.md` (KISS, YAGNI): **don't build a migration engine for
migrations that don't exist.** Build the seam, not the content behind it.

## What to build

`src/absicht/migrate.py`:

- A tiny registry: `MIGRATIONS: dict[int, Callable[[dict], dict]]` (or a
  small `Migration` protocol if that reads better) mapping *from-version* to
  a function that upgrades one version's raw record dict to the next. Empty
  today — `{}` — and a comment explaining why, matching the pattern
  `verification.md` describes for the not-yet-armed mutation scope:
  *"arms itself the moment one of them lands — no configuration change, no
  remembering."*
- `ab migrate` at `--to` (default: latest known version, i.e.
  `SCHEMA_VERSION`) against a store already at that version: `OK`, no-op,
  says so. Against a store at a version with no registered migration path:
  `USAGE` — "don't know how to migrate from N", not a crash.
- `--dry-run`: report what *would* change without writing — meaningful once
  a real migration exists; with the registry empty, it's the same "already
  current" report either way, and that's fine.
- `ab check` (once [`15-check-cli.md`](15-check-cli.md) lands) reads
  `schema_version` off loaded records and should be the thing surfacing
  `ExitCode.SCHEMA_MISMATCH` when a store predates the running binary's
  schema — confirm that's wired up in `check`, since `migrate`'s help text
  ("run `ab migrate`") is the advice `SCHEMA_MISMATCH`'s exit-code
  description in `cli.md` implies, and the loop only closes if both ends
  exist. If `15-check-cli.md` already landed without this, it's a small
  follow-up in that command, not a reason to duplicate schema-version
  detection here.

## Out of scope

- No actual field-renaming/reshaping migration logic — there is exactly one
  schema version. This task is the harness, ready for version 2 whenever it
  exists.

## Tests

- `ab migrate` against a `06-fixtures.md` system already at
  `SCHEMA_VERSION`: `OK`, reports "already current."
- `ab migrate --to 99` (a version with no path): `USAGE`.
- `--dry-run` doesn't write anything (assert the store's files are
  byte-identical before/after).

## Definition of done

- `tests/test_cli.py`: `migrate` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
