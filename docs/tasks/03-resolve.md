# 03 — `absicht.resolve`

## Depends on
[00-conventions.md](00-conventions.md), [02-load.md](02-load.md).

## Goal

Turn a `LoadedStore` into the `Design` artifact `models.py` already defines,
plus the indexes that `show`, `list`, `gaps`, `trace` and `render` all need
and shouldn't each reimplement: id → element lookup, and the reverse-reference
index ("what points at this ref") that `Element`'s own fields don't carry
(refs are one-directional by design — a `Component` doesn't know which
`Requirement.realized_by` names it).

## What to build

`src/absicht/resolve.py`:

- `resolve(loaded: LoadedStore) -> Design` — assembles the `Design` pydantic
  model from the loaded tuples. Raises (or returns an error path — pick one
  and be consistent with how `LoadError` is handled one layer down; probably
  a `ResolveError` distinct from `LoadError`, since "the store didn't parse"
  and "the store parsed but has no `system.yaml`" are different failures) if
  `loaded.system` is `None` — a `Design` requires a `system` field, there's
  no meaningful build without it.
- `Index` — built from a resolved `Design`: `by_id: dict[Ref, object]` (every
  element from every kind, keyed by its own `id`), and
  `referenced_by: dict[Ref, tuple[Ref, ...]]` — for every ref-typed field on
  every element (`realized_by`, `constrains`, `derived_from`, `contains`,
  `consumes`, `provides`, `owns_data`, `satisfies`, `scope`, `applies_to`,
  `supersedes`, `blocks`, `resolved_by`, `includes`, `must_hold`,
  `depends_on`, `owner_component`, `provider`, `consumers`, `carries`,
  `touches`, `externals` on `System`, `units` — walk `models.py` rather than
  hand-copying this list, it will drift) record, for the target id, which
  source id pointed at it and (useful for `trace`) via which field name. This
  is *not* validation — a ref that doesn't resolve just doesn't appear as a
  key; [`13-check-integrity.md`](13-check-integrity.md) is what turns a
  dangling ref into a finding.
- `Index.orphaned(kind: Kind | None = None) -> tuple[Ref, ...]` — ids with no
  entry in `referenced_by` (used by `ab list --orphaned`).
- Something `trace` can walk directionally — either expose `by_id` +
  `referenced_by` and let [`24-trace.md`](24-trace.md) do its own BFS, or add
  a small `neighbours(ref, *, direction) -> tuple[Ref, ...]` helper here if
  the traversal logic is genuinely shared with `gaps --blocking`. Don't build
  a general graph library; this project's graphs are small and the need is
  narrow (see CLAUDE.md: no abstraction beyond what's needed).

## Out of scope

- No cycle detection here — that's a `check` integrity rule
  ([`13-check-integrity.md`](13-check-integrity.md)), because a cycle is a
  *finding*, and `resolve` should still produce a `Design` for `check` to
  report against even when one exists. Don't make `resolve` raise on a cycle.
- No git/`--rev` awareness — `resolve` takes whatever `load` handed it.

## Tests

- `resolve()` over each `06-fixtures.md` system produces a `Design` with the
  expected element counts, and `resolve()` over the broken fixture raises/
  reports the missing-`system` case if that fixture exercises it (or add a
  dedicated tiny fixture for "store with no system.yaml" if the four
  06-fixtures systems don't already cover it — check before assuming).
- `Index.referenced_by` finds a `Requirement.realized_by` pointing at a
  `Component`, and a dangling ref (points at an id that doesn't exist in
  `by_id`) is simply absent from the index rather than raising.
- `Index.orphaned()` matches a hand-constructed small `Design` where exactly
  one component is unreferenced.

## Definition of done

- `absicht.resolve` added to the import-linter layers list, above
  `absicht.load`.
- `./scripts/verify.sh` clean.
