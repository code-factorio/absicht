# 22 — `ab list KIND`

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md),
[20-build.md](20-build.md).

## Spec
> - `--state STATE` repeatable
> - `--confidence LEVEL`
> - `--owner WHO` / `--unowned`
> - `--tag TAG` repeatable
> - `--milestone REF` members of a milestone's scope
> - `--orphaned` nothing refers to it
> - `--format {text,json,ids}` `ids` for piping
>
> — [`../spec/cli.md`](../spec/cli.md#ab-list-kind)

## What to build

Replace `unimplemented(ctx)` in `list_elements()`, `src/absicht/cli/query.py`:

- Pull the tuple for `KIND` off the resolved `Design` (a small
  `Kind → field name` lookup — `Design`'s field names already match
  `Kind.value` almost exactly per
  [`00-conventions.md`](00-conventions.md)'s directory-layout table; confirm
  the one mismatch, `nfr` vs `non_functionals`, is handled).
- Apply filters in whatever order is cheapest, all are simple predicate
  ANDs: `--state` (any-of, since it's repeatable — an element matches if its
  state is in the given set), `--confidence` (exact), `--owner` (exact) /
  `--unowned` (`owner is None`; mutually exclusive with `--owner`, `USAGE`
  if both given), `--tag` (any-of over `Element.tags`), `--milestone REF`
  (element's id appears in that milestone's `scope`), `--orphaned`
  (`Index.orphaned()` from [`03-resolve.md`](03-resolve.md)).
- `--format text` (human table), `json` (list of resolved elements,
  enveloped), `ids` (one id per line, nothing else — this is the format an
  agent scripting `ab list component --orphaned --format ids | xargs ab
  show` depends on; keep it exactly that plain, no headers, no trailing
  whitespace weirdness).

## Out of scope

- No sorting flag in the spec — pick one stable default (id order is the
  obvious, deterministic choice) and don't add a `--sort` flag nobody asked
  for.

## Tests

- Each filter independently, against `tests/fixtures/systems/brownfield/`
  (it has the state/ownership variety to make filters meaningful) —
  `--unowned` finds the ungoverned `unknown`, `--orphaned` finds the
  disconnected elements the fixture was built to have.
- `--owner` and `--unowned` together is `USAGE`.
- `--format ids` output is exactly one id per line, parses back with
  `.splitlines()` to the expected set with no extras.
- `--milestone REF` against `clean/`'s milestone returns exactly its
  `scope`.

## Definition of done

- `tests/test_cli.py`: `list` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
