# 46 — `ab marker stamp`

## Depends on
[44-marker-sync.md](44-marker-sync.md), [05-git.md](05-git.md) (for
`design_rev`).

## Spec
> `ab marker stamp --repo PATH --unit REF --milestone REF` move the
> watermark; run from the commit that lands the work
>
> `design_rev` is a watermark, not a pin. It records where the code caught
> up to... A runner bumps both in the commit that lands the work —
> evidence, produced by the thing that produced the change.
>
> — [`../spec/cli.md`](../spec/cli.md#ab-marker), README's Discovery section

## What to build

Add to `src/absicht/markers.py`:

- `stamp(repo: Path, unit: Ref, milestone: Ref, *, design_rev: str) ->
  Marker` — read the existing `.absicht` at `repo` (must exist — stamping a
  repo with no marker is `USAGE`, run `marker sync` first), find the
  `UnitWatermark` for `unit` (missing → `USAGE`, the unit isn't tracked by
  this marker), set `at=milestone`, `design_rev=design_rev`, write back.
- The CLI (`marker_stamp()`, `src/absicht/cli/reconcile.py`) supplies
  `design_rev` — the spec doesn't list a `--design-rev` flag, which means
  it's computed, not passed: current design-repo `HEAD` via
  [`05-git.md`](05-git.md)'s `current_rev()`, run against the *design
  store's* repo, not `--repo` (which is the implementing repo receiving the
  stamp — these are two different git repos in reference mode, don't
  conflate them; re-read the README's Discovery section, `design_rev` is
  explicitly "design head at the time it landed," i.e. the design store's
  commit, not the implementing repo's).
- `milestone` should resolve against the store (`USAGE` if it doesn't
  exist) — this command's whole job is recording *evidence*, so recording a
  claim about a milestone that doesn't exist is worth catching immediately
  rather than silently writing garbage a later `ab status` can't make sense
  of.

## Out of scope

- No verification that the milestone's `done_when` is actually satisfied —
  the spec and `CONTEXT.md` are explicit that a watermark *over-claims* by
  nature (*"a merge stamps it whether or not the work was finished"*) and
  that's an accepted, documented property, not a bug this command should
  try to prevent. Don't add a check here that the spec doesn't ask for.

## Tests

- Stamping a tracked unit updates exactly that unit's `at`/`design_rev`,
  leaves every other unit in the marker untouched.
- Stamping an untracked unit, or a repo with no marker at all, or a
  nonexistent milestone: each `USAGE`, distinctly worded.
- `design_rev` matches the design store repo's `HEAD` at invocation time
  (test against a throwaway git fixture per [`05-git.md`](05-git.md)'s
  pattern, not this repo's own commit history).

## Definition of done

- `tests/test_cli.py`: `marker stamp` removed from the "not implemented"
  parametrization.
- `./scripts/verify.sh` clean.
