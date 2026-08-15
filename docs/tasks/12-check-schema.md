# 12 — `absicht.check`: the schema layer

## Depends on
[00-conventions.md](00-conventions.md), [02-load.md](02-load.md),
[04-findings.md](04-findings.md).

## Goal

The first of `ab check`'s three layers: *"fields, types, patterns."* This is
the layer with the least new logic to write — `pydantic` already enforces
field types and the `Ref`/`Slug`/`CriterionId` patterns at parse time, inside
[`01-codec.md`](01-codec.md)/[`02-load.md`](02-load.md). This task's job is
to turn the `LoadError`s that loading already produces into `Finding`s, not
to re-implement validation `pydantic` already did.

## Spec
> Runs three layers: schema (fields, types, patterns), integrity..., and
> policy...
>
> — [`../spec/cli.md`](../spec/cli.md#ab-check)

## What to build

`src/absicht/check.py` (this task starts the module; 13 and 14 add to it):

- `schema_findings(loaded: LoadedStore) -> tuple[Finding, ...]` — map each
  `LoadError` to a `Finding` with `severity=Severity.ERROR` (a file that
  doesn't parse is never advisory), `rule_id` distinguishing *what kind* of
  schema problem it was where that's cheap to tell apart (e.g.
  `schema/yaml-syntax` vs `schema/validation` — `CodecError`'s subclasses
  from [`01-codec.md`](01-codec.md) should make this straightforward; if
  `codec` only exposes one error type, this task's scope includes going back
  and splitting it, since "what checks does this rule check, and why" is
  exactly what `--explain` needs to answer per rule).
- Register each schema rule id + explanation in the
  `absicht.findings.RuleCatalog` (or whatever [`04-findings.md`](04-findings.md)
  named it).
- Confirm (write a test for it, don't just assume) that a `pydantic`
  `ValidationError`'s message survives the `CodecError` → `Finding` chain in
  a form that names the offending field, not just "validation failed" — an
  agent fixing a store from a `Finding.message` needs to know which field.

## Out of scope

- No integrity checks (ref resolution, cycles, criterion anchoring beyond
  what `Story`'s own validator already does at parse time) —
  [`13-check-integrity.md`](13-check-integrity.md).
- No policy checks — [`14-check-policy.md`](14-check-policy.md).
- No CLI wiring (`--rule`, `--format`, exit codes) —
  [`15-check-cli.md`](15-check-cli.md).

## Tests

- Against `tests/fixtures/systems/broken/` (see
  [`06-fixtures.md`](06-fixtures.md)): each deliberately-malformed file
  produces exactly one schema `Finding` naming the right rule id and field.
- Against `clean/` and `brownfield/`: zero schema findings — both fixtures
  are meant to parse cleanly even though `brownfield` has plenty for the
  *policy* layer to say later.

## Definition of done

- `absicht.check` added to the import-linter layers list, above
  `absicht.load` (it will also end up above `absicht.resolve` once
  [`13-check-integrity.md`](13-check-integrity.md) lands — add that
  dependency then, not preemptively, since this task doesn't import
  `resolve`).
- `./scripts/verify.sh` clean.
