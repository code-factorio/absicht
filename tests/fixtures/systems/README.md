# Fixture systems

The four stores every task tests against instead of inventing ad hoc ones
(`docs/tasks/00-conventions.md`, *Fixtures*; the shapes are
`docs/tasks/06-fixtures.md`'s). Each is a hand-authored `.absicht/` tree in
the format `00-conventions.md` pins: `system.yaml` as plain YAML, one
`<slug>.md` file per element under its kind directory.

- **`clean/`** — small, complete, internally consistent: every ref resolves,
  every criterion is anchored to its own story, every element `specified` or
  `constrained`. Nothing here should ever produce a finding.
- **`brownfield/`** — an honest reading of a legacy system: `observed`
  elements without rationale, one `unknown` requirement with no owner (the gap
  `ab gaps` exists to surface), orphaned elements nothing points at. Loads
  without errors; the findings it should produce are policy *warnings* for
  `ab check`, not load failures.
- **`broken/`** — two files fail at load time, on purpose:
  `requirements/garbage.md` is not valid YAML, and `stories/bad-anchor.md`
  carries a criterion anchored to another story (rejected by `Story`'s own
  validator, i.e. at parse time). The rest of `broken/` parses fine but is
  deliberately invalid at the *check* layer — `components/dangling.md` points
  at a component that does not exist, `decisions/one-way-no-why.md` is a
  `one_way` decision with no rationale body, `externals/expired.md` carries an
  assumption whose expiry has passed. Load must not flag those three; a later
  `ab check` must.
- **`composite/`** — one design over two units: a `system.yaml` with two
  `units`, a seam whose provider and consumer sit in different units, one
  external assumption. The multi-repo path `status`, `verify --repo` and the
  marker commands will need.
