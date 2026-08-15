# 40 — `absicht.verify`: scaffolding

## Depends on
[00-conventions.md](00-conventions.md), [04-findings.md](04-findings.md),
[05-git.md](05-git.md), [31-packet-assembly.md](31-packet-assembly.md) (for
the `Packet`/`packet.lock` shapes this reads).

## Goal

`ab verify` is, per `CONTEXT.md`, *"the entire premise of the project"* —
the one check that asks whether the code is the code that was asked for,
not just whether it's well-formed. This task builds the scaffolding: loading
a sealed packet, resolving the diff to check against, multi-repo handling,
rule filtering, and report rendering. [`41-verify-rules.md`](41-verify-rules.md)
fills in the actual rule bodies against this scaffolding — split the same
way [`12`](12-check-schema.md)–[`15`](15-check-cli.md) split `check`, for
the same reason: the rules are the part with real judgement calls, the
plumbing around them isn't.

## Spec
> - `--packet PATH` default: the sealed packet in the build dir
> - `--repo PATH` repeatable, for multi-repo slices
> - `--diff-base REF` what counts as "this change". Default `origin/HEAD`
> - `--rule ID` / `--exclude-rule ID`
> - `--strict` warnings become errors
> - `--format {text,json,sarif}`
> - `--report PATH` write the reconciliation report
>
> `ab verify` must run offline against a fetched packet, in CI, in
> somebody else's repo.
>
> — [`../spec/cli.md`](../spec/cli.md#ab-verify), `CONTEXT.md`

## What to build

`src/absicht/verify.py`:

- `load_sealed_packet(path: Path) -> tuple[Packet, PacketLock]` — reads the
  packet body + `packet.lock` written by
  [`32-packet-cli.md`](32-packet-cli.md)'s `--seal`. **This must not require
  network or the design store** — everything a rule needs has to already be
  in the packet or computable from the diff/repo alone, which is the whole
  point of sealing. If a rule (in 41) turns out to need something not in
  the sealed packet, that's a signal the packet's shape (or `--seal`'s
  contents) is missing a field — flag it rather than reaching back into a
  live store connection.
- A `VerifyContext` bundling: the loaded `Packet`, the resolved diff
  (changed files, via [`05-git.md`](05-git.md)'s `changed_paths` against
  `--diff-base`), and the set of `--repo PATH`s (each is a filesystem path
  to an implementing repo's working tree — for a single-repo/embedded
  project this is just `.`; multi-repo slices pass several).
- Rule functions in [`41-verify-rules.md`](41-verify-rules.md) will each
  have the shape `(ctx: VerifyContext) -> tuple[Finding, ...]` — same
  pattern as `absicht.check`'s layers, reusing `absicht.findings.Finding`/
  `Report` directly (no second report type).
- CLI wiring in `verify()`, `src/absicht/cli/reconcile.py`: load the
  packet, build the context, run the (initially empty, until 41 lands)
  rule list filtered by `--rule`/`--exclude-rule`, render per `--format`,
  `--report PATH` writes the rendered report to a file *in addition to*
  stdout (not instead of — the flag says "write," the format flags already
  govern what goes to stdout), exit via `Report.exit_code(strict=--strict)`.
- `--packet` default: `.absicht/build/packets/<milestone>/packet.lock`'s
  sibling packet — but *which* milestone, if none is named on the command
  line? Re-read `cli.md`'s `verify` spec: there's no `MILESTONE` argument at
  all, only `--packet PATH`. So "the sealed packet in the build dir" must
  mean: if exactly one sealed packet exists under
  `.absicht/build/packets/*/packet.lock`, use it; if zero or more than one,
  `USAGE` and say so — don't guess which milestone was meant.

## Out of scope

- No rule implementations — [`41-verify-rules.md`](41-verify-rules.md).
- No network/store access from within a rule — see above.

## Tests

- `load_sealed_packet` round-trips a `packet.lock` written by
  [`32-packet-cli.md`](32-packet-cli.md)'s tests.
- The "exactly one sealed packet, else USAGE" default-discovery logic,
  tested with zero, one, and two candidates in `tmp_path`.
- `--report PATH` writes the file *and* stdout still shows the rendered
  report (assert both, don't assume `--report` implies quiet).
- Rule filtering (`--rule`/`--exclude-rule`) exercised against a couple of
  fake rule functions registered for the test, so this task's tests don't
  have to wait on 41's real ones to prove the plumbing works.

## Definition of done

- `absicht.verify` added to the import-linter layers list.
- `./scripts/verify.sh` clean.
