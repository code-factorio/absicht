# 21 — `ab show REF`

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md),
[20-build.md](20-build.md) (reuses its `load → resolve` path — every query
command in this block does; don't reimplement it per command, extract a
shared `absicht.query`-internal helper or just call `absicht.build.build`'s
in-memory pieces directly).

## Spec
> One element, resolved: its own fields, what points at it, what it points
> at.
>
> - `--format {text,json,md}`
> - `--depth N` how far to follow refs. Default `1`
> - `--body` / `--no-body`
>
> — [`../spec/cli.md`](../spec/cli.md#ab-show-ref)

## What to build

Replace `unimplemented(ctx)` in `show()`, `src/absicht/cli/query.py`:

- Resolve `REF` against `Index.by_id`; unknown ref is `USAGE` (a bad
  argument, not a design finding — consistent with the exit-code table's
  intent).
- "What it points at": the element's own ref-typed fields, resolved to the
  actual elements (not just the ids) — depth 1 means one hop.
- "What points at it": `Index.referenced_by[REF]`, resolved the same way.
- `--depth N > 1`: follow further hops from whichever of the above sets a
  higher depth extends (the spec is terse here — "how far to follow refs" —
  so the reasonable reading is a breadth-first expansion of the *outgoing*
  side, since "what points at it" already only makes sense one level without
  it becoming a full reverse-trace; if this feels underspecified while
  implementing, that's real — consider whether `--depth` should behave
  identically in both directions or only expand outward, and document
  whichever you pick in the command's own `--help`, since the spec doesn't
  pin it and a future reader shouldn't have to guess from the code).
- `--format text` (human, default), `json` (the full resolved+neighbours
  structure, `schema_version`-enveloped per
  [`00-conventions.md`](00-conventions.md)), `md` (a single Markdown
  document — this is the shape [`26-render-site.md`](26-render-site.md)'s
  element pages will likely reuse; factor the Markdown rendering so it's
  callable from both rather than writing it twice).
- `--body`/`--no-body`: include/omit the element's prose body in the output
  (default: include).

## Out of scope

- No traversal beyond direct refs into a general path-finding graph search —
  that's `ab trace`'s job ([`24-trace.md`](24-trace.md)), which explicitly
  finds *paths between two elements*; `show` is a neighbourhood view, not a
  pathfinder.

## Tests

- Against `tests/fixtures/systems/clean/`: a component's `show` output lists
  the requirement that `realized_by`s it (inbound) and the seams it
  `provides` (outbound).
- Unknown ref is `USAGE`.
- `--no-body` omits the element's prose in all three formats.
- `--depth 2` reaches a second hop that `--depth 1` doesn't, on a fixture
  element chosen to have one.

## Definition of done

- `tests/test_cli.py`: `show` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
