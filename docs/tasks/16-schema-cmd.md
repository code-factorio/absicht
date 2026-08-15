# 16 — `ab schema`

## Depends on
[00-conventions.md](00-conventions.md). No dependency on `load`/`resolve` —
this command only reflects on `absicht.models`, it never reads a store.

## Spec
> Emit JSON Schema for the file formats. Commit the output so editors give
> autocomplete and inline errors while authoring.
>
> - `--out DIR` default `schema/`
> - `--check` fail if the committed schema is stale
>
> — [`../spec/cli.md`](../spec/cli.md#ab-schema)

## What to build

Replace `unimplemented(ctx)` in `schema()`, `src/absicht/cli/author.py`:

- For each concrete `Element`/`Record` subclass a store file can hold
  (everything `Kind` names, plus `System`, `Marker` — walk `models.py`
  rather than hand-listing, same principle as
  [`03-resolve.md`](03-resolve.md)'s field enumeration), emit
  `Model.model_json_schema()` to `<out>/<kind>.schema.json`. Pydantic does
  the actual schema generation; this command's job is deciding the file
  layout and writing it deterministically (stable key order — pydantic's
  output should already be deterministic per model, confirm rather than
  assume, especially around `$defs` ordering for nested types).
- `--check`: regenerate in memory, compare against what's committed under
  `schema/` (or `--out` if given — though `--check` presumably always
  compares against the *committed* location regardless of `--out`; read the
  flag combination and decide, `--out` together with `--check` is a slightly
  odd pairing worth a short comment either way), exit `FINDINGS` if any
  file differs, listing which.
- Without `--check`: write the files, exit `OK`.

## Out of scope

- No YAML-editor-specific packaging (e.g. VS Code extension manifests) —
  "commit the output so editors give autocomplete" just means the JSON
  Schema files exist in the repo at a stable path; wiring an editor to them
  is the user's `.vscode/settings.json` or equivalent, not this command's
  problem.

## Tests

- Emits one file per element kind, each valid JSON, each round-trippable
  back through a JSON Schema validator's basic structural checks (a
  `"type"` key, a `"properties"` key — no need for a full external
  validator dependency, `json.loads` plus a shape assertion is enough).
- `--check` against an up-to-date `schema/` (fixture: run the command once,
  commit the output as a test fixture, then run `--check` in the test) is
  `OK`; edit one committed file in a `tmp_path` copy first, `--check` is
  `FINDINGS` and names the stale file.
- Output is byte-identical across two runs (determinism — the same
  standard every artifact in this project holds itself to, per
  `verification.md`).

## Definition of done

- `tests/test_cli.py`: `schema` removed from the "not implemented"
  parametrization.
- Decide whether the generated `schema/*.schema.json` files themselves get
  committed to the repo now (the spec says "commit the output," so yes —
  run the command for real once this lands and commit its output in the
  same PR, not just the code that produces it).
- `./scripts/verify.sh` clean.
