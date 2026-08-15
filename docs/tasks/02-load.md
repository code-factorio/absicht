# 02 — `absicht.load`

## Depends on
[00-conventions.md](00-conventions.md), [01-codec.md](01-codec.md).

## Goal

Walk a store — a `.absicht/` directory on the working tree, or (later, via
`absicht.git`) the same tree at a revision — and turn it into raw per-kind
collections of parsed elements, tolerant of individual bad files. This is the
layer that makes `ab check`'s schema findings possible: a store with one
broken file should report one finding, not crash the whole command.

## What to build

`src/absicht/load.py`:

- `LoadError` — a small record: `path: str`, `message: str` (wraps whatever
  `absicht.codec.CodecError` said). Doesn't know about `absicht.findings`
  severities; that translation happens in `absicht.check`, one layer up —
  `load` stays usable by `build` and `packet` too, which don't want a
  `Finding` shape, just data plus a list of things that went wrong.
- `LoadedStore` — a container: one tuple per `Kind` (`components:
  tuple[Component, ...]`, etc., mirroring `Design`'s fields minus `system`),
  plus `system: System | None` (None if `system.yaml` is missing or
  unparsable — a store without one is a store `build` can't fold, but `load`
  itself should still return what it could read, with the failure recorded
  in `errors`), `layout: Layout | None` if a `Layout`/positions model exists
  by the time this lands (see [`25-layout.md`](25-layout.md) — if that
  hasn't landed yet, load `layout.yaml` as a raw dict or skip it; don't block
  on a model that doesn't exist), and `errors: tuple[LoadError, ...]`.
- `load_store(root: Path) -> LoadedStore` — walks the directory layout from
  `00-conventions.md`, one kind directory at a time, in a stable order
  (sorted filenames — determinism matters everywhere downstream, see
  [`20-build.md`](20-build.md)). A missing kind directory is not an error
  (empty tuple); a file that fails to parse is a `LoadError`, not a raised
  exception — the walk continues.
- Handle `--store` resolution rules from `cli.md`'s Global flags table here
  or in `absicht.cli` — your call, but land it *somewhere* rather than
  leaving `DEFAULT_STORE` as the only path ever tried: `.absicht/` as a
  directory (embedded), else `.absicht` as a file (reference — read the
  `Marker`, resolve to the store it names; resolving a *remote* `design:` URL
  is out of scope here, treat it as "not yet supported, fail clearly" unless
  a later task adds it), else no store found (`ExitCode.USAGE`, per the exit
  code table).

## Out of scope

- No `--rev` support in this task — `load_store` takes a `Path` on the
  working tree. [`05-git.md`](05-git.md) lands a parallel entry point (or an
  optional `rev` parameter backed by it); don't block this task on that one,
  but leave the seam obvious (e.g. `load_store` reads through a small
  `FileSource` protocol rather than calling `Path.read_text` inline, so `git`
  can supply an alternate implementation later without `load.py` changing
  shape). Don't build the abstraction further than that one seam needs.
- No cross-reference resolution — raw per-kind tuples only. That's
  [`03-resolve.md`](03-resolve.md).
- No writing. `load` is read-only, always.

## Tests

- Loading each of the four `06-fixtures.md` systems produces the expected
  counts per kind and, for the deliberately-broken one, the expected
  `LoadError`s (path + a message that names what was wrong, not a stack
  trace repr).
- An embedded store with no `system.yaml` loads everything else and reports
  the missing system as one `LoadError`, doesn't crash.
- A reference-mode `.absicht` file resolves to the store it names for a
  *local* path (a `design:` field pointing at a filesystem path or an
  already-checked-out git remote is fine to support now; a bare URL that
  needs fetching is explicitly future work — say so in a docstring, don't
  silently half-implement it).
- `--store` env var fallback (`ABSICHT_STORE`) and the directory-vs-file mode
  detection are exercised — this is core to the project's whole "watermark"
  story, get the `stat()` logic right and tested, not assumed.

## Definition of done

- `absicht.load` added to the import-linter layers list, positioned above
  `absicht.codec`.
- `./scripts/verify.sh` clean.
