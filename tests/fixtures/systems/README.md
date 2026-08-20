# Fixture systems

The four stores every test works against instead of inventing ad hoc ones.
Each is a hand-authored `.absicht/` tree in the format `absicht.codec` pins:
`design.yaml` as plain YAML, one `<slug>.md` file per element under its kind
directory, each element's outgoing edges in its own `relates` block.

- **`clean/`** — small, complete, internally consistent: every ref resolves,
  every requirement is implemented by a component and realized by a behavior,
  every goal is measured and served, every element `specified` and `reviewed`.
  `ab check` reports one `info` line and nothing else — the advisory count,
  which exists precisely so a `should` observation stays visible. It carries
  the C4 nesting chain (`component:acme` system, two containers, one
  component), one interface with operations, two resources — a store and a
  stream, so `effective_timing` has both defaults to answer with — and three
  behaviors: `behavior:order-placed-v2` supersedes and composes the older
  `behavior:order-placed`, whose observations between them exercise `must`,
  `must_not` and `should`.
- **`brownfield/`** — an honest reading of a legacy system: `observed`
  elements with no rationale, one `unknown` requirement with no owner (the gap
  `ab gaps` exists to surface, and the one thing here `ab check` grades an
  error), the orphaned `data:audit-log` nothing points at, two open questions
  — one blocking `milestone:reconcile-mvp`, one blocking nothing — one
  external service whose assumptions lapsed (`external:payment-api`, the
  counterpart to `composite/`'s current one), one `observed` behavior
  (`behavior:reconciliation-fires`, what an import of an undocumented system
  produces), and one note in the inbox. It loads without errors: `observed`
  being unexplained is the honest brownfield default, not a broken file.
- **`broken/`** — one clearly-named file per failure family, so a test can
  point `--rule X` at exactly the case that trips it. Three files fail at load
  time, on purpose, and can never reach the graph layer:
  `requirements/garbage.md` is not valid YAML (`store/yaml-syntax`);
  `behaviors/bad-anchor.md` carries an observation anchored to another
  behavior and `behaviors/bad-timing.md` a `must_not` that says when — both
  refused by the records' own validators (`store/validation`). The rest parse
  fine and are invalid only at the check layer:

  - `components/dangling.md` — an `implements` edge onto `req:ghost`
    (`integrity/dangling-ref`), the same rule an observation's dangling `at`
    trips through `behaviors/dangling-observation.md`.
  - `components/loop-a.md` + `components/loop-b.md` — each nested in the
    other: one `integrity/cycle` for the one loop, plus the level rule each
    file breaks on its own.
  - `components/wrong-repo.md` — `implemented_by` names a repository
    `design.yaml` does not declare (`integrity/repository-unknown`).
  - `components/bad-edge.md` — a `calls` edge onto a resource
    (`integrity/edge-kinds`).
  - `interfaces/legacy-cache.md` — declared by a resource, which takes part
    in no contract (`integrity/interface-on-resource`). The ref resolves —
    the defect is the kind it points at.
  - `behaviors/observation-at-decision.md` — an `at` that resolves, to
    something nobody can watch (`integrity/observation-target`).
  - `behaviors/supersede-a.md` + `behaviors/supersede-b.md` — each replaces
    the other (`integrity/cycle`), and `behaviors/compose-loop-a.md` + `-b.md`
    the same shape through composition.
  - `behaviors/no-observations.md` — says something happens and never says
    what (`policy/behavior-unobserved`).
  - `requirements/no-behavior.md` — implemented by `component:audits` and
    realized by nothing (`policy/requirement-unrealized`), so it trips
    exactly one rule.
  - `goals/unserved.md` — no measure (`policy/goal-unmeasured`); the
    requirement above derives from it, which keeps `policy/goal-unserved`
    quiet.
  - `questions/unowned-unknown.md` — `unknown`, nobody to ask
    (`policy/unknown-unowned`).
  - `decisions/one-way-no-why.md` — `constrained` with no `reversibility`
    (`policy/agency-undeclared`).
  - `external_services/expired.md` — `expires_on` in the past
    (`policy/external-assumption-expired`).
  - `milestones/unscoped.md` — no `scope` (`policy/milestone-unscoped`, and
    `packet/empty-scope` for anyone assembling from it).

  Everything else here is `specified` and owned, so each file above trips its
  own rule and nothing else's.
- **`composite/`** — one design over two repositories: `design.yaml` declares
  both, `component:orders-api` is implemented in one and
  `component:billing-worker` in the other, and the interface between them is
  declared on one side and called from the other. It also carries the one
  external service that is verified and current. Repository membership is
  derivable from `implemented_by` alone, the way `status`, `verify --repo` and
  the marker commands need it.
