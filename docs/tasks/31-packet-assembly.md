# 31 — `absicht.packet`: assembly

## Depends on
[00-conventions.md](00-conventions.md), [03-resolve.md](03-resolve.md),
[04-findings.md](04-findings.md) (packet assembly can hit real problems —
a milestone with no scope, a horizon that can't be satisfied — worth
representing the same way `check` represents them, even though `ab packet`
itself doesn't expose `--rule` the way `check`/`verify` do; reuse the
`Finding` shape where it fits rather than inventing a third error
vocabulary).

## Goal

The core of the whole project, per the README: *"The unit of output is the
packet... A human or a coding agent can act on a packet without reading the
whole system and without guessing at the parts that were never written
down."* This task builds the `Packet` (the `models.py` type already exists)
from a `Design` and a milestone ref. [`32-packet-cli.md`](32-packet-cli.md)
is the thin CLI wrapper, rendering, `--seal`, and `--rev`.

## Spec
> Assemble the brief: milestone scope at full fidelity, one ring of
> neighbouring contracts, the decisions and NFRs that must hold, explicit
> freedoms, known unknowns, and the rejections that must not be
> re-proposed.
>
> - `--horizon N` rings of contract-fidelity neighbours. Default `1`
> - `--include REF` / `--exclude REF` force an element in or out; repeatable
>
> — [`../spec/cli.md`](../spec/cli.md#ab-packet-milestone)

## What to build

`src/absicht/packet.py`:

- `assemble(design: Design, index: Index, milestone: Ref, *, horizon: int,
  include: frozenset[Ref], exclude: frozenset[Ref]) -> Packet`:
  - **Full-fidelity scope**: every element in `Milestone.scope`, plus the
    milestone itself, at `Fidelity.FULL` (the full element, all fields).
  - **Contract-fidelity ring(s)**: elements one (or `--horizon N`) hop
    outward from scope via the graph — concretely, the seams/components/
    externals that scope-members `consume`/are `consumed by`, but only at
    `Fidelity.CONTRACT`: per the `Fidelity` enum's own docstring in
    `models.py`, *"the seam, nothing behind it"* — meaning a neighbour
    outside scope contributes its contract-relevant fields (a `Seam`'s
    `contract`/`style`/`failure_modes`, say) but not its full internals.
    Decide, per element kind, which fields count as "contract" vs "behind
    it" — this is a real design call the spec doesn't spell out per-field;
    write it down as a short table in the module docstring once decided, so
    it's not re-litigated per bug report.
  - `--horizon N`: repeat the ring expansion N times, each additional ring
    still at `Fidelity.CONTRACT` (only the *first* ring out from the actual
    scope is "neighbouring" in the strictest reading — re-check the spec
    line, "one ring" is the default and N generalizes it, so N rings all at
    contract fidelity, none of them promoted to full, is the consistent
    reading).
  - `--include`/`--exclude`: applied after the horizon computation — force
    an element to `Fidelity.FULL` if included (even if it wouldn't
    otherwise be in scope), or drop it entirely if excluded (even if the
    horizon would have pulled it in). `--include` and `--exclude` naming
    the same ref is `USAGE`.
  - **`must_hold`**: decisions and NFRs relevant to scope — `Decision`s
    whose `applies_to` intersects scope, `NonFunctional`s whose `scope`
    does, plus whatever `Milestone.must_hold` names directly (the milestone
    can name these explicitly too, per its own field — union the two
    sources, don't pick one).
  - **`may_decide`**: `Milestone.may_decide` verbatim.
  - **`unresolved`**: `Milestone.unresolved` verbatim (open questions
    knowingly left open — the packet tells the agent about them rather than
    hiding them).
  - **`rejections`**: `Rejection`s whose `applies_to` intersects scope, or
    whose own `milestone` field names this milestone, "the rejections that
    must not be re-proposed" per spec.
  - **`criteria`**: behavioural + structural + measured criteria belonging
    to stories/milestones in scope (`Milestone.done_when` plus each in-scope
    `Story.acceptance`).
  - A milestone ref that doesn't resolve, or resolves to a milestone with
    empty `scope`, is a clear failure (which `ExitCode` — `USAGE` for "ref
    doesn't exist," arguably `FINDINGS` for "milestone exists but is
    unusable as a packet target," e.g. empty scope — decide and be
    consistent with how [`32-packet-cli.md`](32-packet-cli.md) maps this to
    an exit code).

## Out of scope

- No Markdown/JSON rendering, no `--seal`, no `--rev` — the packet is
  assembled from an already-resolved in-memory `Design`; feeding it one
  built at a past revision is [`32-packet-cli.md`](32-packet-cli.md)'s job,
  via [`05-git.md`](05-git.md).
- No Gherkin — [`30-gherkin.md`](30-gherkin.md), invoked by the CLI layer.

## Tests

- Against `tests/fixtures/systems/clean/`'s milestone: the assembled
  `Packet.elements` contains exactly the expected refs at exactly the
  expected `Fidelity`, at `--horizon 1` and `--horizon 2` (choose/extend the
  fixture so these differ meaningfully).
- `--include`/`--exclude` each override what the horizon computation would
  otherwise produce; naming the same ref in both is `USAGE`.
- `must_hold`/`rejections`/`unresolved` each pull from both the milestone's
  own field and the derived (applies_to/scope-intersection) source, and
  the union is deduplicated.
- A milestone with empty `scope` and a milestone ref that doesn't exist are
  each handled distinctly and predictably.

## Definition of done

- `absicht.packet` added to the import-linter layers list.
- `./scripts/verify.sh` clean.
