# 11 — `ab new`

## Depends on
[00-conventions.md](00-conventions.md), [01-codec.md](01-codec.md),
[03-resolve.md](03-resolve.md) (to check for id collisions against the
existing store before writing).

## Spec
> Create an element from a template, with a generated id.
>
> Kinds: `component seam data requirement nfr story decision rejection
> question milestone external`
>
> - `--title TEXT`
> - `--state STATE` default `unknown`
> - `--owner WHO`
> - `--edit` open `$EDITOR`
> - `--print` write to stdout instead of the store
>
> — [`../spec/cli.md`](../spec/cli.md#ab-new-kind-slug)

## What to build

`src/absicht/new.py` (or a function in `absicht.codec`/`absicht.init` — see
the judgement note in [`10-init.md`](10-init.md), same applies here):

- `id = f"{kind}:{slug}"` per
  [`00-conventions.md`](00-conventions.md#identity). Construct the minimal
  valid instance of the model for `kind` (e.g. `Component(id=..., title=...,
  state=..., owner=...)`) — every other field at its pydantic default. If a
  kind's model requires a field with no sensible default (check each model
  in `models.py`; most required fields beyond `id`/`title` are Ref
  collections that default to `()`, so this should mostly be mechanical, but
  confirm rather than assume), populate it with the smallest valid
  placeholder and say so in a template comment in the body, not by silently
  fabricating something that would pass `check` without a human ever looking
  at it.
- `--print`: render via `absicht.codec.dump_element` to stdout, don't touch
  the store — useful for an agent that wants to see the shape before
  deciding to write it, and for scripting (`ab new component x --print | ab
  something`).
- Default (no `--print`): write to `<store>/<kind-dir>/<slug>.md`. Fail
  (`ExitCode.USAGE`) if the id already exists in the store (load + check
  `by_id`, per [`03-resolve.md`](03-resolve.md)) or if the file path already
  exists — those should be the same condition in a healthy store, but check
  the one you're about to write to, not just the index, in case the store
  and filesystem have drifted.
- `--edit`: after writing (or before, for `--print`'s case — decide: editing
  something you're about to print to stdout instead of a file is a stretch;
  `--edit` most likely only makes sense combined with the store-write path,
  so consider making `--edit --print` together a `USAGE` error rather than
  guessing what the user meant), shell out to `$EDITOR` on the written file
  path. If `$EDITOR` is unset, fail clearly (`USAGE`) rather than silently
  doing nothing — a command that says `--edit` and doesn't open anything is
  worse than one that tells you why.

## Out of scope

- No interactive prompting for fields beyond what the flags cover — this is
  a scaffolding command for an agent or a human with an editor, not a wizard.
- No criteria authoring (`Story.acceptance`) — `ab new story` produces a
  story with no acceptance criteria; adding them is `--edit`'s job, by hand.

## Tests

- `ab new component cancellation-flow --title "..."` writes exactly one
  file at the expected path with the expected front matter.
- `--print` writes to stdout, leaves the store directory untouched (assert
  no new file exists).
- Colliding slug against an existing element is `USAGE`, not an overwrite —
  `ab new` never overwrites, same principle as `ab init`.
- Every value in the `Kind` enum produces a loadable, `codec.parse_element`-
  round-trippable file — parametrize the test over `Kind`, don't test one
  kind and assume the rest follow.
- `--edit` with `$EDITOR` unset in the test environment is `USAGE` with a
  clear message (monkeypatch `os.environ` to control this rather than
  relying on the ambient test environment's `$EDITOR`).

## Definition of done

- `tests/test_cli.py`: `new` removed from the "not implemented" surface
  parametrization.
- `./scripts/verify.sh` clean.
