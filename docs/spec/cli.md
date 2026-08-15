# absicht — CLI surface

Binary: `ab`. Store: `.absicht/` unless told otherwise.

Two audiences with different needs. A human runs these to author and look
around. An agent or CI runs them to get bounded work in and verification out —
so every command supports `--json` and exits with a meaningful code, and no
command needs a terminal.

Commands are grouped by the step that introduces them. Nothing before step 3 is
required to hand an agent useful work.

## Global flags

| Flag | Meaning |
| --- | --- |
| `--store PATH` | Design store root. Default `.absicht`, then `$ABSICHT_STORE` |
| `--rev REF` | Read the store at a git revision instead of the working tree |
| `--json` | Machine output on stdout. Diagnostics stay on stderr |
| `--quiet` `-q` | Errors only |
| `--verbose` `-v` | Repeatable |
| `--no-color` | Also implied by `NO_COLOR` and a non-tty stdout |
| `--version` | Includes the schema version it speaks |

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success, or advisory findings only |
| `1` | Findings at error severity — validation, verification, drift |
| `2` | Usage error: bad flags, unknown ref, no store |
| `3` | Internal error |
| `4` | Schema version mismatch; run `ab migrate` |

`1` versus `2` matters: CI treats the first as a real result and the second as
a broken pipeline.

---

## Step 1 — author and validate

### `ab init`

Scaffold a store.

- `--name NAME` system name
- `--force` write into a non-empty directory

### `ab new KIND SLUG`

Create an element from a template, with a generated id.

Kinds: `component` `seam` `data` `requirement` `nfr` `story` `decision`
`rejection` `question` `milestone` `external`

- `--title TEXT`
- `--state STATE` default `unknown`
- `--owner WHO`
- `--edit` open `$EDITOR`
- `--print` write to stdout instead of the store

### `ab check`

Validate the store. The core command — everything else assumes it passed.

Runs three layers: schema (fields, types, patterns), integrity (every ref
resolves, no cycles in `contains` or `depends_on`, criteria anchored to their
story), and policy (an `unknown` needs an owner, a requirement needs a
realizing component, a `one_way` decision needs a rationale body, an external's
assumptions have not expired).

- `--rule ID` `-r` only these rules; repeatable
- `--exclude-rule ID` repeatable
- `--severity {error,warn,info}` minimum reported. Default `warn`
- `--strict` treat warnings as errors
- `--changed-only` only elements touching the diff against `--diff-base`
- `--diff-base REF` default `origin/HEAD`
- `--format {text,json,sarif}` sarif for code-scanning annotations
- `--explain ID` print what a rule checks and why, then exit

### `ab schema`

Emit JSON Schema for the file formats. Commit the output so editors give
autocomplete and inline errors while authoring.

- `--out DIR` default `schema/`
- `--check` fail if the committed schema is stale

### `ab migrate`

- `--to N` default: latest
- `--dry-run`

---

## Step 2 — build, query, look at it

### `ab build`

Fold the store into one normalized JSON document. Deterministic — same input,
byte-identical output. Everything downstream reads this and nothing else.

- `--out PATH` default `.absicht/build/design.json`
- `--stdout`
- `--check` build and diff against the existing artifact; non-zero if it moved

### `ab show REF`

One element, resolved: its own fields, what points at it, what it points at.

- `--format {text,json,md}`
- `--depth N` how far to follow refs. Default `1`
- `--body` / `--no-body`

### `ab list KIND`

- `--state STATE` repeatable
- `--confidence LEVEL`
- `--owner WHO` / `--unowned`
- `--tag TAG` repeatable
- `--milestone REF` members of a milestone's scope
- `--orphaned` nothing refers to it
- `--format {text,json,ids}` `ids` for piping

### `ab gaps`

Everything unfinished, as a worklist: `unknown`, `observed`, `delegated`, open
questions, unowned elements, expired external assumptions.

- `--kind KIND` `--owner WHO` `--overdue`
- `--blocking REF` only gaps that block this element or milestone
- `--format {text,json}`

### `ab trace REF`

Traceability paths through the graph: requirement to component to seam to
decision, in either direction.

- `--to REF` paths between two elements
- `--up` / `--down` direction. Default both
- `--format {text,json,mermaid}`

### `ab render`

Generate the read-only site: element pages, traceability, gaps, diagrams.

- `--out DIR` default `.absicht/build/site`
- `--serve` `--port N` local preview with rebuild on change
- `--overlay {state,milestone,coverage,churn}` repeatable; same layout,
  different colouring
- `--format {svg,mermaid,d2}` diagram output
- `--scope REF` render one subtree

### `ab layout`

Positions are design data, not a rendering detail. Stable layout is what makes
the diagrams worth having — if boxes move on every build, spatial memory never
forms.

- `--recompute` re-run the deterministic layout for new elements only
- `--recompute-all` throw away pinned positions
- `--seed N`
- `--check` fail if any element has no position

---

## Step 3 — hand work to an agent

### `ab packet MILESTONE`

Assemble the brief: milestone scope at full fidelity, one ring of neighbouring
contracts, the decisions and NFRs that must hold, explicit freedoms, known
unknowns, and the rejections that must not be re-proposed.

- `--out DIR` default `.absicht/build/packets/<milestone>`
- `--stdout`
- `--format {md,json}` default `md`; `json` for programmatic consumers
- `--horizon N` rings of contract-fidelity neighbours. Default `1`
- `--include REF` / `--exclude REF` force an element in or out; repeatable
- `--features` / `--no-features` emit `.feature` files from behavioural
  criteria. Default on
- `--features-dir DIR` default `features/`
- `--rev REF` build from the store at a revision
- `--seal` write `packet.lock` — design rev plus the scenario digest, so
  `ab verify` can run offline later

### `ab features MILESTONE`

Render behavioural criteria to Gherkin without the rest of the packet. Output is
generated, never authored: an agent implements step definitions and may not
touch these files.

- `--out DIR` `--stdout`
- `--check` fail if emitted output differs from what is on disk

---

## Step 4 — verify what came back

### `ab verify`

The half no generic quality gate can do. Everything else asks whether the code
is well-formed; this asks whether it is the code that was asked for.

Checks: the diff touched only components in scope; nothing marked
`out_of_scope` was built; nothing was built on an `unknown` without a recorded
decision; every seam in scope has a contract test that runs; every `done_when`
criterion has something verifying it; scenario files are unmodified against the
sealed digest; step definitions contain assertions.

- `--packet PATH` default: the sealed packet in the build dir
- `--repo PATH` repeatable, for multi-repo slices
- `--diff-base REF` what counts as "this change". Default `origin/HEAD`
- `--rule ID` / `--exclude-rule ID`
- `--strict` warnings become errors
- `--format {text,json,sarif}`
- `--report PATH` write the reconciliation report

### `ab status`

Where the code stands against the design, computed from watermarks and
implementation refs.

Reports units behind design head, which decisions and seam changes landed since
each watermark, seams whose consumers have not caught up, components with no
implementation reference, and milestones with unmet `done_when`.

A watermark is a hint, not proof — it tends to over-claim, since a merge stamps
it whether or not the work was finished.

- `--repo PATH` repeatable
- `--unit REF` one unit
- `--behind-only`
- `--since REF` compare against a specific design rev instead of watermarks
- `--fail-on-drift` non-zero when anything is behind. For CI
- `--format {text,json}`

### `ab diff REF_A REF_B`

What changed in the design between two revisions, as elements rather than lines:
decisions added, seams whose contract moved, requirements added or dropped,
state transitions.

- `--scope REF` limit to a subtree
- `--kind KIND`
- `--format {text,json,md}`

### `ab marker`

Manage `.absicht` discovery files in implementing repos. The store stays
authoritative; markers are regenerable hints.

- `ab marker sync --repo PATH` write or update from the store
- `ab marker check --repo PATH` fail if a marker disagrees with the store
- `ab marker stamp --repo PATH --unit REF --milestone REF` move the watermark;
  run from the commit that lands the work

---

## Later

- `ab import --repo PATH` brownfield extraction: structure from code,
  everything intent-shaped lands as `observed` or `unknown`
- `ab mine --repo PATH` candidate decisions from git history, PRs and ADR
  folders, with provenance and confidence, for a human to accept or kill
- `ab serve` the webapp, once there is something worth looking at

## Notes

`--json` output is versioned and additive. Agents parse it, so a field never
changes meaning — it gets deprecated and a new one appears.

No command mutates the store as a side effect of reading. `check`, `build`,
`packet`, `verify` and `status` are all safe to run anywhere, any number of
times.

No command in this list needs a network or an LLM.
