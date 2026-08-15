# 10 — `ab init`

## Depends on
[00-conventions.md](00-conventions.md), [01-codec.md](01-codec.md).

## Spec
> Scaffold a store. The mode is chosen, not inferred.
> - `--embedded` store as `.absicht/` in this repo. Default
> - `--reference URL` write an `.absicht` file pointing at the store at
>   `URL`; `ab marker sync` fills in the units
> - `--name NAME` system name
> - `--force` write into an existing `.absicht/`. Adds files, deletes none
>
> `init` never overwrites. An existing `.absicht` stops it... `--force`
> relaxes only the empty-store case.
>
> — [`../spec/cli.md`](../spec/cli.md#ab-init)

Note: the current CLI signature in `src/absicht/cli/author.py` is missing
`--embedded` and `--reference URL` — only `--name` and `--force` are wired
up. Add the missing options as part of this task; `cli.md` is the contract,
the signature was scaffolded ahead of the body and evidently didn't carry
every flag over. Update `tests/test_cli.py`'s `SURFACE["init"]` flag list to
match once you've added them.

## What to build

`src/absicht/init.py` (or fold into `absicht.codec`/`absicht.build` if it
turns out to be a two-function module not worth its own file — use
judgement, don't force a module for its own sake):

- Embedded mode: create the directory layout from
  [`00-conventions.md`](00-conventions.md) (empty kind directories, or just
  the ones that will be written to first — an empty directory a `Kind` has
  no elements for yet doesn't need to exist ahead of time, since `load`
  already treats a missing kind directory as "no elements", per
  [`02-load.md`](02-load.md)) plus a `system.yaml` built from `--name` (a
  `System` with that title/id and sensible defaults for everything else —
  decide what `System.id` should be when only a display name is given;
  `system:<slugified-name>` is the obvious rule, consistent with
  [`00-conventions.md`](00-conventions.md#identity)).
- Reference mode (`--reference URL`): write a `.absicht` file (a `Marker`
  with `design: URL`, `units: ()`) via `absicht.codec.dump_singleton`. Don't
  create a `.absicht/` directory in this mode — the whole point is that the
  store lives elsewhere.
- The mutual-exclusion / never-overwrite rule from the spec: fail
  (`ExitCode.USAGE`) if `.absicht` (file) and `.absicht/` (directory) — check
  both, they can't coexist but a stale one from a previous failed run could
  — already exists and isn't empty, unless `--force`, which per the spec
  "relaxes only the empty-store case": re-read that line carefully, it does
  **not** mean force-overwrite-anything, it means force past the
  already-exists check for a store that has no elements in it yet. Get this
  distinction right; it's the one subtle rule in an otherwise mechanical
  command.
- `--embedded` and `--reference` should be mutually exclusive
  (`typer`/`click` can enforce this, or check manually and exit `USAGE`).

## Out of scope

- No remote fetch for `--reference URL` — writing the marker file is all
  `init` does; `ab marker sync` (see [`44-marker-sync.md`](44-marker-sync.md))
  is what "fills in the units" per the spec.

## Tests

- Embedded init in an empty `tmp_path` creates `system.yaml` with the right
  name/id and no unexpected files.
- Running it twice without `--force` in the same directory is `USAGE`, not a
  silent overwrite; twice *with* `--force` on an empty store succeeds; with
  `--force` on a store that already has elements still refuses (re-read the
  spec line above — this is the case worth a dedicated test).
- `--reference URL` writes exactly a `.absicht` file, no directory.
- `--embedded --reference URL` together is `USAGE`.
- `--json` output includes `schema_version` and names the mode and path
  created.

## Definition of done

- `tests/test_cli.py`: `init` removed from the "not implemented" surface
  parametrization; `SURFACE["init"]` flags updated if `--embedded`/
  `--reference` were missing.
- `./scripts/verify.sh` clean.
