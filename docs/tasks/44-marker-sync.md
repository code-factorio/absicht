# 44 — `ab marker sync`

## Depends on
[00-conventions.md](00-conventions.md), [01-codec.md](01-codec.md),
[03-resolve.md](03-resolve.md).

## Goal

The first of three `marker` subcommands
([`45-marker-check.md`](45-marker-check.md),
[`46-marker-stamp.md`](46-marker-stamp.md) build on it). Write/update the
`.absicht` discovery file — a `Marker` (already modeled in `models.py`) — in
an implementing repo, from the design store. This is what the README's
Discovery section calls *"a marker an agent dropped into an implementing
repo reads to find its design without being told where to look."*

## Spec
> Manage `.absicht` discovery files in implementing repos. The store stays
> authoritative; markers are regenerable hints.
>
> `ab marker sync --repo PATH` write or update from the store
>
> — [`../spec/cli.md`](../spec/cli.md#ab-marker)

## What to build

`src/absicht/markers.py`:

- `sync(design: Design, repo: Path, *, design_url: str) -> Marker` — for
  every `Component` whose `implemented_by` names a path under `repo` (the
  `"repo#path"` format from `Component.implemented_by`'s docstring in
  `models.py` — parse the `#` split, match the repo half against `repo`'s
  identity, however that's determined; this may need `repo`'s own git
  remote URL or a configured name, since a bare filesystem path passed via
  `--repo PATH` isn't necessarily the same string stored in
  `implemented_by` — decide how the match is made and document it, this is
  a real seam between the design store's notion of "which repo" and the
  CLI's `--repo PATH` argument), build a `UnitWatermark(id=component.id,
  path=<the matched path>, at=<preserve existing watermark's `at`/
  `design_rev` if a marker already exists there — sync must not silently
  reset watermarks to null, that's `marker stamp`'s job, not sync's>)`.
- Write the resulting `Marker` to `<repo>/.absicht` via
  `absicht.codec.dump_singleton`. If a `.absicht/` *directory* (embedded
  mode) already exists at that path instead of a file, this is `USAGE` —
  sync never converts a store's own repo into a marker-holding repo, the
  two modes are exclusive per the README's Discovery section.
- **Preserving existing watermarks is the one thing this command must get
  right** — re-read the spec line: *"write or update."* An update means
  units gain/lose entries as `implemented_by` changes, but a unit that's
  in both the old and new marker keeps its `at`/`design_rev`. Losing a
  watermark on every sync would silently erase `ab status`'s only source of
  truth about what's landed.

## Out of scope

- No watermark advancement — that's `ab marker stamp`
  ([`46-marker-stamp.md`](46-marker-stamp.md)), which moves `at`/
  `design_rev` for one unit. `sync` only adds/removes/repaths units; it
  never changes a `design_rev` value it finds already present.

## Tests

- Against a fresh `repo` (no `.absicht` yet): sync creates one with
  `units` matching the design's `implemented_by` entries pointing at that
  repo, `at`/`design_rev` unset (`None`) for all of them — nothing to
  preserve yet.
- Against a `repo` with an existing marker naming a watermark: sync
  preserves that watermark for units still present, drops units no longer
  referenced, adds units newly referenced (with no watermark).
- Against a `repo` where `.absicht/` is a directory: `USAGE`.

## Definition of done

- `absicht.markers` added to the import-linter layers list.
- `tests/test_cli.py`: `marker sync` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
