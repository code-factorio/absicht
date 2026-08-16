# Fixture systems

The four stores every task tests against instead of inventing ad hoc ones
(`docs/tasks/00-conventions.md`, *Fixtures*; the shapes are
`docs/tasks/06-fixtures.md`'s). Each is a hand-authored `.absicht/` tree in
the format `00-conventions.md` pins: `system.yaml` as plain YAML, one
`<slug>.md` file per element under its kind directory.

- **`clean/`** — small, complete, internally consistent: every ref resolves,
  every criterion is anchored to its own story, every element `specified` or
  `constrained`. Nothing here should ever produce a finding — it is the store
  a rule's "does not trip" case runs against.
- **`brownfield/`** — an honest reading of a legacy system: `observed`
  elements without rationale, one `unknown` requirement with no owner (the gap
  `ab gaps` exists to surface), orphaned elements nothing points at
  (`component:shadow-report`, `data:audit-log`), two open questions — one past
  its `due_on` and blocking the not-yet-committed `milestone:reconcile-mvp`,
  one still inside its (far-future) due date — and one external whose
  assumptions expired in the past (`external:payment-api`, the counterpart to
  `composite/`'s current one and the fixture `ab gaps --overdue`,
  `--blocking` and the `external-expired` reason run against). Loads without
  errors; the findings it should produce are policy *warnings* for `ab check`,
  not load failures — `observed` being unexplained is the honest brownfield
  default.
- **`broken/`** — one clearly-named file per failure family, so a later
  `ab check` task can point `--rule X` at exactly the case that trips it.
  Two files fail at load time, on purpose: `requirements/garbage.md` is not
  valid YAML, and `stories/bad-anchor.md` carries a criterion anchored to
  another story — rejected by `Story`'s own validator at parse time, so that
  family is exercised at the load/codec layer and can never reach the check
  layer. The rest parse fine and are deliberately invalid only at the
  *check* layer:

  - `components/dangling.md` — `contains` names `component:ghost`, which
    does not exist (`integrity/dangling-ref`).
  - `components/loop-a.md` + `components/loop-b.md` — each `contains` the
    other: one cycle for the integrity layer to find, not one finding per
    edge.
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
  policy rule. Load must not flag any of the five; `ab check` must.
- **`composite/`** — one design over two units: a `system.yaml` with two
  `units`, a seam whose provider and consumer sit in different units, one
  external assumption that is verified and current (the counterpart to
  `broken/`'s expired one). Both sides of the seam name a `repo#path`
  (`acme/orders#api`, `acme/billing#worker`), so unit membership is
  derivable the way the multi-repo path `status`, `verify --repo` and the
  marker commands will need.
