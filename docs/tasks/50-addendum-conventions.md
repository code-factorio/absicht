# 50 — Addendum conventions every 5x/6x task shares

Not a command, not a module. Read this — after
[`00-conventions.md`](00-conventions.md), which still applies in full —
before starting any task numbered 51–60. It pins the decisions the
[model addendum](../spec/ABSICHT-MODEL-ADDENDUM.md) leaves to implementation,
so they get made once instead of differently by every task.

The addendum is the spec for this block. Read it whole before any 5x/6x task;
each task quotes its section but the argument only closes over the full
document. The one-line version: three new things in the model — **Resource**
(an addressable thing we depend on but do not design), **Behavior** (an
expectation about how the system acts, carrying **Observations**), and
**Note** (deliberately *not* an element) — plus derived scope, lifecycle /
supersession, and a local run store for packets and verification runs.

## Reality check: the addendum vs the code

The addendum was written against an older mental model. Two of its claims are
already stale against `src/absicht/models.py`:

- §7 says "Currently only `Question` carries an owner." Not true: `Element`
  already has `owner: str | None`, inherited by every kind. What §7 still
  asks for is the *inheritance* rule (an `unknown` inherits the owner of the
  element it sits on, one level, no deeper) and owner-grouping in queries —
  see [`55-addendum-query-surface.md`](55-addendum-query-surface.md).
- §0's table says structs live in `model/` as msgspec. They live in
  `src/absicht/models.py` as pydantic. (CONTEXT.md had the same staleness;
  it has been fixed.)

As always: trust the code over any doc, including this one.

## On-disk layout additions

Extending the layout pinned in `00-conventions.md`, same one-element-per-file
front-matter format:

```
.absicht/
├── resources/            # Resource elements
├── behaviors/            # Behavior elements, observations inline
└── notes/                # notes — committed, but NOT elements
```

Observations are authored **inline in their behavior's file**, as an
`observations:` list in the front matter — the same shape as a story's
`acceptance:` criteria. There is no `observations/` directory and no
free-standing observation file; an observation without its behavior is
meaningless.

Notes are one file per note, `notes/<slug>.md`: front matter is `id`,
optional `ref`, `created`, optional `promoted_to` — nothing else. Body is the
note. No title, no state, no owner, no tags: the addendum's capture-friction
rule ("the moment authoring a note asks for classification it stops being
used") is a hard constraint, not a preference.

## Identity

- Resource / behavior ids follow the existing rule: `resource:<slug>`,
  `behavior:<slug>`, slug authored via `ab new`.
- Observation ids anchor to their behavior exactly as criteria anchor to
  their story: `behavior:new-chat-session#obs-2`, pattern
  `^[a-z]+:[a-z0-9][a-z0-9-]*#obs-\d+$` (a new `ObservationId` type next to
  `CriterionId`), with a `Behavior` model validator mirroring
  `Story._criteria_anchored_to_story`.
- Note ids are **generated, never asked for**: `note:` plus six lowercase
  base36 characters (`note:a1b2c3`), drawn at random and collision-checked
  against the store. Not derived from content — editing a note must not
  change its identity. This is the one place identity is not
  deterministic-from-slug, and the friction rule is why.

## New enums, and where defaults live

| Enum | Values | Home |
|---|---|---|
| `ResourceKind` | `store` `endpoint` `stream` | `models.py` |
| `Outcome` | `must` `must_not` `should` | `models.py` |
| `Timing` | `immediate` `eventual` | `models.py` |
| `Lifecycle` | `active` `superseded` | `models.py` |

`kind` on a resource is load-bearing (addendum §1.2): things branch on it.
Anything merely descriptive goes in `technology` (free text, forever — §1.1)
or a tag. Do not add a fourth `ResourceKind` value without a spec change.

`Observation.timing` is optional on the model. The *effective* timing is
computed, not stored: an authored value wins; otherwise the default follows
the resource kind the observation points at (`store`/`endpoint` →
`immediate`, `stream` → `eventual`, per §1.2's table); anything not pointing
at a resource defaults to `immediate`. For `outcome: must_not`, `timing`
must be **absent** — presence is a check error (§3.1), because `must_not`
means "at no point".

## Derived, never stored

Same inversion discipline as `parent` with no `children[]`:

- **Behavior scope** (`local` / `system`) is computed from the union of the
  behavior's observations' `at` refs — one component, no resources, no seams
  → `local`; anything else → `system`. No field, no author choice (§4.1).
- **`superseded_by`** is derived from other behaviors' `supersedes`; only
  the replacement side is stored (§5).
- **The packet's must-not-break list** is computed from active behaviors
  whose observations touch the components/seams/resources in scope (§5).

Derived values appear in `--json` output and on the site; they never appear
in a file an author edits, and the codec must never write them.

## Milestone selection of behaviors

The addendum says a milestone "selects which behaviors a slice must newly
satisfy" but not where. Pinned: behaviors are named in `Milestone.includes`,
alongside the stories and requirements already allowed there. No new
milestone field. The must-satisfy set is `includes` filtered to
`behavior:` refs; must-not-break is derived (above) minus must-satisfy.

## Notes are outside the graph — structurally, not by convention

`Note` is a `Record`, not an `Element`. Notes are **not** part of `Design`,
not in the build artifact, not in `resolve`'s `Index`, and never packet
input. `LoadedStore` carries them as a separate collection so `ab note` and
the single note check rule (`promoted_to` must resolve) can see them. The
`note` kind is not added to `absicht.cli._common.Kind` — `ab note` is its
own command group, and `ab new note` / `ab list note` must not exist.

## The run store

§8's "local store beside the design store" is SQLite at
`.absicht/build/runs.db` — inside the already-gitignored build directory, so
nothing new needs ignoring and it is destroyed by exactly the actions that
destroy other derived artifacts. Two tables, matching §8's tuples:
`packets(milestone, design_rev, packet_id, issued_at, target_agent)` and
`runs(packet_id, commit_sha, criterion, result, evidence_ref)`. Losing it
loses run history, not design. Module: `absicht.runstore`, sitting low in
the layer stack (above `models`, beside `git`) so both `packet` and `verify`
can reach it.

## Check rule ids

Follow the existing `layer/rule-name` naming in `check.py` / `findings.RULES`.
The addendum's rules, named once here so 54 and later tasks agree:

| Rule id | Severity | Addendum |
|---|---|---|
| `integrity/seam-references-resource` | error | §1.4 |
| `integrity/observation-at-unresolvable` | error | §3.2 (subsumed by `integrity/dangling-ref` if the generic walk covers observation refs — if so, register as handled-upstream like `integrity/criteria-anchored`) |
| `integrity/observation-at-wrong-kind` | error | §3.2 — `at` pointing at a requirement, decision, question (or note) |
| `integrity/composition-cycle` | error | §4.2 |
| `integrity/supersedes-unresolvable` | error | §5 (same subsumption note) |
| `integrity/supersession-cycle` | error | §5, includes self-supersession |
| `integrity/note-promoted-to-unresolvable` | error | §6 |
| `schema/must-not-has-timing` | error | §3.1 — enforceable at parse time by an `Observation` model validator; register as handled-upstream if so |
| `policy/behavior-needs-observations` | error | §2 |
| `policy/requirement-needs-behavior` | warn | §2 |
| `policy/superseded-in-must-satisfy` | error | §5 |

## Layer stack additions

New modules and where they slot into `pyproject.toml`'s
`[[tool.importlinter.contracts]]` list (same rule as ever: added in the same
commit that creates them):

- `absicht.runstore` — beside `absicht.git`, above only `models`.
- Notes handling lives in existing layers (`codec`, `load`) plus a small
  `absicht.notes` module for the add/promote/drop operations, sitting with
  the other store-writing modules (`new`, `init`).

## Renderers last

The addendum's own rule: "A design that is only reachable through the
browser is a defect", and renderers land "last, not first". Every 5x task
must make its addition authorable and readable from the CLI with `--json`
before [`60-addendum-render.md`](60-addendum-render.md) touches the site.
