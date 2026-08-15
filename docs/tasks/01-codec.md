# 01 — `absicht.codec`

## Depends on
[00-conventions.md](00-conventions.md) (file format, layer stack).

## Goal

The single place that knows how an element is spelled on disk. Everything
above this layer works with `pydantic` models from `absicht.models`;
everything below it (there is nothing below it but `models` itself) never
sees a `Path` or a YAML document. This is what CONTEXT.md means by *"Schema in
exactly one place"* and what keeps the file format swappable later.

## What to build

`src/absicht/codec.py`:

- `dump_element(element: Element) -> str` — render one element to the on-disk
  text format from `00-conventions.md` (YAML front matter, minus `source` and
  `body`, then `---`, then the body verbatim). Field order in the front
  matter should be stable (declaration order on the model) so diffs stay
  small — don't let a dict's iteration order decide it.
- `parse_element(text: str, *, model: type[E], source: str) -> E` — the
  inverse. Splits front matter from body, parses the YAML, constructs the
  model with `source` set from the passed-in path and `body` set from the
  parsed body text, and lets `pydantic`'s own validation raise on anything
  malformed. Generic over the element type (`E: TypeVar`) so a caller passing
  `model=Component` gets a `Component` back, not `Element`.
- `dump_singleton(record: Record) -> str` / `parse_singleton(text: str, *,
  model: type[R]) -> R` — for `system.yaml` and `layout.yaml`: plain YAML,
  no front-matter/body split (see `00-conventions.md`).
- A `CodecError` exception (or a small hierarchy) that wraps whatever the
  underlying YAML parser and `pydantic.ValidationError` raise, carrying
  enough to build a `absicht.findings.Finding` one layer up without
  `absicht.load` having to know pydantic's exception shape directly. Keep
  this thin — it's a translation, not a validation framework of its own.
- Pick and add a YAML library (`pyyaml` most likely — check what's already
  implied by `dev` deps in `pyproject.toml`; none is currently a runtime
  dependency, so add it to `[project.dependencies]`, not `dev`). Use
  `yaml.safe_load` — never `yaml.load` without a `Loader`, that's an
  arbitrary-code-execution footgun `bandit`'s `security` check exists to
  catch.

## Out of scope

- No filesystem walking (that's [`02-load.md`](02-load.md)) — `codec`
  functions take text/paths as arguments, never a store root.
- No cross-element validation (ref resolution, cycles) — that's
  `absicht.check`, per `models.py`'s own module docstring.
- No git integration — `codec` doesn't know a revision exists.

## Tests

- Round-trip: for a representative element of each `Kind` (and `System`,
  `Marker`/`UnitWatermark`), `parse_element(dump_element(x)) == x`.
- A file with a body but no front matter, front matter but no body, and
  neither, all parse to sensible results (empty body / empty-ish front
  matter — decide and assert, don't leave it implicit).
- A YAML syntax error and a `pydantic` validation error both raise
  `CodecError` (or your named subclass), not a raw parser exception leaking
  through — that's the whole point of the wrapper.
- Front-matter field order is stable across two calls to `dump_element` on
  equal-but-differently-constructed elements.

## Definition of done

- `absicht.codec` added to the `pyproject.toml` import-linter layers list.
- `./scripts/verify.sh` clean.
- New runtime dependency (YAML library) declared in `[project.dependencies]`,
  `uv.lock` updated (`uv lock`).
