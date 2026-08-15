# 04 — `absicht.findings`

## Depends on
[00-conventions.md](00-conventions.md).

## Goal

One vocabulary for "something is wrong", shared by `ab check` and `ab
verify` — the two commands that produce a graded report rather than a
listing. Building this once means `--format {text,json,sarif}`, `--strict`,
`--severity`, and the `FINDINGS` vs `USAGE` exit-code split are each
implemented once too.

## What to build

`src/absicht/findings.py`:

- `Finding` — frozen record: `rule_id: str`, `severity: Severity` (reuse
  `absicht.cli._common.Severity` — don't fork a second severity enum; if that
  means `findings` needs to sit where it can import from `cli._common`
  without breaking the layer contract, move the value-only enums that both
  sides need somewhere both can reach, e.g. keep `Severity` importable from
  `cli._common` but have `findings.py` depend on it directly since it's a
  bare `StrEnum` with no CLI logic — confirm this doesn't violate
  `import-linter`'s layering before committing to it; if it does, the enum
  belongs in `models.py` or a new tiny shared module instead, and
  `cli._common` re-exports it), `message: str`, `ref: str | None = None`
  (the element the finding is about, when there is one), `source: str | None
  = None` (file path, from the element's provenance), `rule_explain: str`
  (what `--explain ID` prints — see [`15-check-cli.md`](15-check-cli.md)).
- `Report` — `findings: tuple[Finding, ...]`, plus:
  - `filtered(*, rules: set[str] | None, exclude: set[str], min_severity:
    Severity) -> Report`
  - `exit_code(*, strict: bool) -> ExitCode` — `FINDINGS` if any finding is
    `error`, or (when `strict`) `warn`; else `OK`.
  - `render_text() -> str`, `render_json() -> dict[str, object]` (with the
    `schema_version` envelope from `00-conventions.md`), `render_sarif() ->
    dict[str, object]` — minimal valid SARIF 2.1.0 (`runs[].results[]` with
    `ruleId`, `level`, `message.text`, `locations[].physicalLocation`), not a
    full SARIF feature sweep. Enough for GitHub code-scanning to annotate a
    line; that's the stated purpose in `cli.md`.
- A small `RuleCatalog` or equivalent — every rule id `check`/`verify` can
  produce, each with a one-line `explain` string, so `--explain ID` (both
  commands... actually only `check` has `--explain` per `cli.md` — confirm
  against the spec before adding it to `verify` too) has something to print
  without duplicating text between the rule implementation and the catalog.
  Keep this simple: a `dict[str, str]` populated by each rule module at
  import time, or a decorator on rule functions, whichever reads more
  plainly. Don't build a plugin system for eleven rules.

## Out of scope

- No rule *logic* here — this module knows how to represent and render a
  finding, not how to produce one. Rules live in `absicht.check` and
  `absicht.verify`.
- No SARIF beyond what code-scanning needs to annotate a diff.

## Tests

- `Report.exit_code` for the four combinations of (has error / has only
  warn) × (strict / not strict).
- `filtered()` composes `--rule`, `--exclude-rule`, `--severity` correctly,
  including the case where the same id is both included and excluded (decide
  precedence — exclude should win, since that's the more specific ask — and
  test it).
- `render_json()`'s top-level shape includes `schema_version`; `render_sarif`
  validates against a minimal hand-written JSON Schema fragment or at least
  has the required top-level keys asserted directly (no need for a SARIF
  validator dependency for this).

## Definition of done

- `absicht.findings` added to the import-linter layers list.
- `./scripts/verify.sh` clean.
