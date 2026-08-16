# Fixture systems

The four stores every task tests against instead of inventing ad hoc ones
(`docs/tasks/00-conventions.md`, *Fixtures*; the shapes are
`docs/tasks/06-fixtures.md`'s). Each is a hand-authored `.absicht/` tree in
the format `00-conventions.md` pins: `system.yaml` as plain YAML, one
`<slug>.md` file per element under its kind directory.

- **`clean/`** — small, complete, internally consistent: every ref resolves,
  every criterion is anchored to its own story, every element `specified` or
  `constrained`. Nothing here should ever produce a finding — it is the store
  a rule's "does not trip" case runs against. Since the model addendum, it
  also carries one resource (`resource:order-cache`) and two behaviors:
  `behavior:order-placed-v2` supersedes — and composes, through an
  observation's `at` — the older `behavior:order-placed`, whose observations
  between them exercise `must`, `must_not`, `should` and both timings.
- **`brownfield/`** — an honest reading of a legacy system: `observed`
  elements without rationale, one `unknown` requirement with no owner (the gap
  `ab gaps` exists to surface), orphaned elements nothing points at
  (`component:shadow-report`, `data:audit-log`), two open questions — one past
  its `due_on` and blocking the not-yet-committed `milestone:reconcile-mvp`,
  one still inside its (far-future) due date — one external whose
  assumptions expired in the past (`external:payment-api`, the counterpart to
  `composite/`'s current one and the fixture `ab gaps --overdue`,
  `--blocking` and the `external-expired` reason run against), and one
  `observed` behavior (`behavior:reconciliation-fires`, what an import of a
  brownfield system produces). Loads without errors; the findings it should
  produce are policy *warnings* for `ab check`, not load failures — `observed`
  being unexplained is the honest brownfield default.
- **`broken/`** — one clearly-named file per failure family, so a later
  `ab check` task can point `--rule X` at exactly the case that trips it.
  Three files fail at load time, on purpose: `requirements/garbage.md` is not
  valid YAML; `stories/bad-anchor.md` carries a criterion anchored to
  another story — rejected by `Story`'s own validator at parse time; and
  `behaviors/bad-timing.md` carries a `must_not` observation with a
  `timing` — rejected by `Observation`'s own validator the same way. Those
  families are exercised at the load/codec layer and can never reach the
  check layer. The rest parse fine and are deliberately invalid only at the
  *check* layer:

  - `components/dangling.md` — `contains` names `component:ghost`, which
    does not exist (`integrity/dangling-ref`).
  - `components/loop-a.md` + `components/loop-b.md` — each `contains` the
    other: one cycle for the integrity layer to find, not one finding per
    edge.
  - `behaviors/dangling-observation.md` — an observation whose `at` names
    `resource:ghost-store`, which does not exist: the generic
    `integrity/dangling-ref` walk covers observation refs, so the finding
    lands on the behavior that carries the observation.
  - `behaviors/observation-at-decision.md` — an observation whose `at`
    resolves, but to a decision: the wrong kind of target (the addendum's
    observation-at-wrong-kind rule, landing with the check addendum).
  - `behaviors/supersede-a.md` + `behaviors/supersede-b.md` — each
    `supersedes` the other: a supersession cycle for the check addendum to
    find, the same shape as the `contains` one above.
  - `seams/legacy-cache.md` — a seam whose `provider` is
    `resource:audit-store`: resources do not participate in seams (addendum
    §1.4; the rule lands with the check addendum). `resources/audit-store.md`
    itself is a well-formed element, so the seam's ref resolves — the defect
    is the kind it points at, not a dangling target.
  - `questions/unowned-unknown.md` — `state: unknown`, no owner
    (`policy/unknown-needs-owner`).
  - `decisions/one-way-no-why.md` — `one_way` with an empty body
    (`policy/one-way-needs-rationale`).
  - `externals/expired.md` — `expires_on` in the past
    (`policy/external-assumptions-expired`).

  Every other element in `broken/` — including `system.yaml` and
  `stories/minimal-story.md`, the story next to the broken one that proves
  the walk continues — is explicitly `specified`, so the unowned unknown
  above is the only thing in this store that can trip an unknown-state
  policy rule. Load must not flag any of the nine; `ab check` must.
- **`composite/`** — one design over two units: a `system.yaml` with two
  `units`, a seam whose provider and consumer sit in different units, one
  external assumption that is verified and current (the counterpart to
  `broken/`'s expired one). Both sides of the seam name a `repo#path`
  (`acme/orders#api`, `acme/billing#worker`), so unit membership is
  derivable the way the multi-repo path `status`, `verify --repo` and the
  marker commands will need.
