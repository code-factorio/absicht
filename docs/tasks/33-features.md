# 33 — `ab features MILESTONE`

## Depends on
[30-gherkin.md](30-gherkin.md), [03-resolve.md](03-resolve.md). Does not
depend on [31](31-packet-assembly.md)/[32](32-packet-cli.md) — this command
only needs the milestone's stories/criteria, not a full packet assembly
(no horizon, no contract ring, no `must_hold` — just the Gherkin half).

## Spec
> Render behavioural criteria to Gherkin without the rest of the packet.
>
> - `--out DIR` `--stdout`
> - `--check` fail if emitted output differs from what is on disk
>
> — [`../spec/cli.md`](../spec/cli.md#ab-features-milestone)

## What to build

Replace `unimplemented(ctx)` in `features()`, `src/absicht/cli/handoff.py`:

- Resolve `MILESTONE`, gather its behavioural criteria the same way
  [`31-packet-assembly.md`](31-packet-assembly.md) does for its `criteria`
  field (`Milestone.done_when` + in-scope stories' `acceptance`) — if 31
  already exposes a reusable "criteria for this milestone" function, call
  that rather than re-deriving it a second time; if this task lands first,
  extract that logic here and have 31 call it back, whichever order the two
  actually land in.
- Render each story's behavioural criteria via
  `absicht.gherkin.render_feature`, write to `--out` (default
  `DEFAULT_FEATURES_DIR`, i.e. `features/`).
- `--stdout`: print instead of writing (all files concatenated with a clear
  separator, or one at a time with filename headers — pick a scriptable
  shape, an agent piping this output should be able to tell where one
  feature file ends and the next begins).
- `--check`: render in memory, diff against what's on disk at `--out`;
  `FINDINGS` (not `USAGE` — this is a real statement about drift, matching
  the exit-code table's intent) if anything differs, naming which files.
  This is the guardrail behind the spec's *"Output is generated, never
  authored... may not touch these files"* — `--check` is how CI catches a
  hand-edit.

## Out of scope

- No packet assembly, no `--seal`, no `--horizon` — this command is
  strictly the Gherkin slice of what `ab packet --features` also does.

## Tests

- Against `clean/`'s milestone: output matches
  [`30-gherkin.md`](30-gherkin.md)'s own snapshot for the same story (same
  renderer, so this is really testing "the CLI wires up the renderer
  correctly," not re-testing Gherkin formatting).
- `--check` against up-to-date files: `OK`. Against a file that's been
  hand-edited (test setup: render once, mutate one line, run `--check`):
  `FINDINGS`, names the file.
- `--stdout` writes nothing to `--out`.

## Definition of done

- `tests/test_cli.py`: `features` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
