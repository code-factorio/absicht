# 32 — `ab packet` (CLI, rendering, `--seal`)

## Depends on
[31-packet-assembly.md](31-packet-assembly.md), [30-gherkin.md](30-gherkin.md),
[05-git.md](05-git.md) (for `--rev`).

## Spec
> - `--out DIR` default `.absicht/build/packets/<milestone>`
> - `--stdout`
> - `--format {md,json}` default `md`; `json` for programmatic consumers
> - `--features` / `--no-features` emit `.feature` files from behavioural
>   criteria. Default on
> - `--features-dir DIR` default `features/`
> - `--rev REF` build from the store at a revision
> - `--seal` write `packet.lock` — design rev plus the scenario digest, so
>   `ab verify` can run offline later
>
> — [`../spec/cli.md`](../spec/cli.md#ab-packet-milestone)

## What to build

Replace `unimplemented(ctx)` in `packet()`, `src/absicht/cli/handoff.py`:

1. `--rev`: build the `Design` at that revision (via
   [`05-git.md`](05-git.md)'s reader path, same seam
   [`20-build.md`](20-build.md) uses) instead of the working tree.
2. Call `absicht.packet.assemble(...)` with `--horizon`/`--include`/
   `--exclude` from the CLI.
3. `--features`/`--no-features`: render `.feature` files via
   [`30-gherkin.md`](30-gherkin.md) into `--features-dir`, relative to
   `--out` (or CWD, when `--stdout` — decide, and be explicit in `--help`
   about where features land when the packet body itself goes to stdout;
   the spec doesn't say features follow `--stdout`, so the reasonable
   default is that `--features-dir` is always a real directory write even
   when `--stdout` covers the packet body).
4. `--format md`: a single Markdown document — milestone outcome, scope
   elements at full detail, contract-ring elements summarized, `must_hold`/
   `may_decide`/`unresolved`/`rejections` as their own sections, criteria
   listed (with a note that the full Gherkin lives in `--features-dir` when
   `--features` is on). `--format json`: `Packet.model_dump()`, enveloped
   per [`00-conventions.md`](00-conventions.md).
5. `--seal`: compute `design_rev` (from `--rev` if given, else
   [`05-git.md`](05-git.md)'s `current_rev()`) and `scenarios_digest` (via
   `absicht.gherkin.scenario_digest` over whatever `.feature` files were
   just rendered — `--seal` without `--features` should probably force
   features on, or fail clearly, since a digest over zero files isn't
   meaningful; decide and document), write `packet.lock` (a small YAML/JSON
   sidecar — pick one and be consistent with the rest of the store's file
   formats; JSON is defensible here since `packet.lock` is machine-read by
   `ab verify`, never hand-authored) into `--out` alongside the packet body.
6. `--out` default is `.absicht/build/packets/<milestone-slug>` per
   `DEFAULT_PACKET_DIR` in `_common.py` — confirm the slug used matches
   what the milestone's own id looks like after stripping the `milestone:`
   prefix, and test that specifically since it's an easy off-by-one.
7. `--stdout`: packet body to stdout, nothing written to `--out` (features/
   `--seal`, if requested, still need *somewhere* to land — see point 3;
   `--stdout --seal` together may simply be `USAGE`, since a seal with
   nowhere durable to put `packet.lock` defeats its own purpose — consider
   that instead of inventing an implicit fallback location).

## Out of scope

- Assembly logic itself — [`31-packet-assembly.md`](31-packet-assembly.md).

## Tests

- End-to-end against `clean/`'s milestone: `--format md` and `--format
  json` both produce a packet with the expected sections/fields; `--seal`
  produces a `packet.lock` whose `design_rev` matches the fixture repo's
  current commit and whose digest matches
  `absicht.gherkin.scenario_digest` computed independently in the test.
- `--rev` against an older commit in a throwaway git fixture (per
  [`05-git.md`](05-git.md)'s test pattern) produces a packet reflecting
  that commit's store, not the working tree's.
- `--stdout --seal` behaves per whatever was decided above — assert the
  actual chosen behavior, don't leave it untested because it was a
  judgement call.

## Definition of done

- `tests/test_cli.py`: `packet` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
