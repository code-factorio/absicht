# 15 — `ab check` (CLI)

## Depends on
[12-check-schema.md](12-check-schema.md), [13-check-integrity.md](13-check-integrity.md),
[14-check-policy.md](14-check-policy.md), [05-git.md](05-git.md) (for
`--changed-only`/`--diff-base`).

## Spec
> The core command — everything else assumes it passed.
>
> - `--rule ID` `-r` only these rules; repeatable
> - `--exclude-rule ID` repeatable
> - `--severity {error,warn,info}` minimum reported. Default `warn`
> - `--strict` treat warnings as errors
> - `--changed-only` only elements touching the diff against `--diff-base`
> - `--diff-base REF` default `origin/HEAD`
> - `--format {text,json,sarif}` sarif for code-scanning annotations
> - `--explain ID` print what a rule checks and why, then exit
>
> — [`../spec/cli.md`](../spec/cli.md#ab-check)

## What to build

Replace `unimplemented(ctx)` in `check()`, `src/absicht/cli/author.py`:

1. `--explain ID` short-circuits everything else: look up `ID` in the
   `RuleCatalog`, print its explanation, exit `OK`. Unknown `ID` is `USAGE`.
2. Otherwise: `load_store` → `resolve` → run `schema_findings` +
   `integrity_findings` + `policy_findings` → combine into one `Report`.
3. `--changed-only`: resolve `--diff-base` via `absicht.git.changed_paths`,
   then filter the report to findings whose `Finding.source` (file path) is
   in that set. A finding with no `source` (a system-wide check, if any ever
   is) — decide whether it survives the filter or not, and be consistent;
   the safer default is to keep source-less findings, since dropping a real
   problem because it can't be attributed to one file is the wrong failure
   mode for a checker.
4. `Report.filtered(rules=--rule, exclude=--exclude-rule, min_severity=--severity)`.
5. Render per `--format`/`--json` (see
   [`00-conventions.md`](00-conventions.md#json-output) for the
   `--json`-vs-`--format` precedence rule — this command is exactly the case
   ADR-0001 was written for).
6. Exit via `Report.exit_code(strict=--strict)`.

## Out of scope

- No new rule logic — this task wires up what 12/13/14 already built.

## Tests

- End-to-end against all four `06-fixtures.md` systems: `clean/` exits `OK`
  with an empty report at every severity; `brownfield/` exits `OK` at
  default severity (warnings only) and `FINDINGS` with `--strict`;
  `broken/` exits `FINDINGS` always.
- `--rule`/`--exclude-rule`/`--severity` each independently change what's in
  the report and, where they cross the error threshold, the exit code.
- `--format sarif` output has the shape `04-findings.md`'s tests already
  cover — here, just confirm the CLI actually calls that renderer and that
  `--json`/`--format json` aren't secretly producing `render_text()`.
- `--changed-only` against a fixture repo (reuse the throwaway-repo pattern
  from [`05-git.md`](05-git.md)'s tests) with a commit that only touches one
  element's file — the report only contains findings about that element.
- `--explain` for a real rule id prints something and exits `OK`; for a
  fabricated id, `USAGE`.

## Definition of done

- `tests/test_cli.py`: `check` removed from the "not implemented"
  parametrization.
- Add "dogfood" is **not** this task's job (that's a CI job named in
  `.github/workflows/ci.yml`'s header comment, run once absicht has its own
  `.absicht/` — separate follow-up, don't scope-creep it in here).
- `./scripts/verify.sh` clean.
