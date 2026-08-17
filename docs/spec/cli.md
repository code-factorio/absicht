# absicht — CLI surface

Binary: `ab`. Store: `.absicht` unless told otherwise.

Two audiences with different needs. A human runs these to author and look
around. An agent or CI runs them to get bounded work in and verification out —
so every command supports `--json` and exits with a meaningful code, and no
command needs a terminal.

Commands are grouped by the step that introduces them. Nothing before step 3 is
required to hand an agent useful work.

## Global flags

| Flag | Meaning |
| --- | --- |
| `--store PATH` | Design store root. Default: `.absicht/` as a directory (embedded), else `.absicht` as a file (reference, resolved to the store it names), else no store. Then `$ABSICHT_STORE` |
| `--rev REF` | Read the store at a git revision instead of the working tree |
| `--json` | Machine output on stdout. Diagnostics stay on stderr. Also accepted on the command itself — `ab check --json` and `ab --json check` are the same thing. See [ADR-0001](../adr/0001-json-on-every-command.md) |
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

Scaffold a store. The mode is chosen, not inferred.

- `--embedded` store as `.absicht/` in this repo. Default
- `--reference URL` write an `.absicht` file pointing at the store at `URL`;
  `ab marker sync` fills in the units
- `--name NAME` system name
- `--force` write into an existing `.absicht/`. Adds files, deletes none

`init` never overwrites. An existing `.absicht` stops it: a marker in reference
mode, a store in embedded mode, and either one where the other mode wants the
name, since one name is one directory entry. `--force` relaxes only the
empty-store case. Switching modes is `ab extract`, or a deletion you make
yourself.

### `ab new KIND SLUG`

Create an element from a template, with a generated id.

Kinds: `component` `seam` `data` `requirement` `nfr` `story` `decision`
`rejection` `question` `milestone` `external` `resource` `behavior`

`resource` and `behavior` come from the
[model addendum](ABSICHT-MODEL-ADDENDUM.md): a resource is an addressable
thing the system depends on but does not design (kind `store` / `endpoint` /
`stream`, technology as free text); a behavior is an expectation about how the
system acts, carrying observations (`behavior:slug#obs-1`) the way a story
carries criteria.

- `--title TEXT`
- `--state STATE` default `unknown`
- `--owner WHO`
- `--edit` open `$EDITOR`
- `--print` write to stdout instead of the store

### `ab note`

Capture a thought against the store with near-zero friction — see the
[model addendum §6](ABSICHT-MODEL-ADDENDUM.md#6-note). Notes are **not
elements**: they are outside the resolved graph, carry no state, and are never
packet input — an agent never sees a note. They are committed, under
`.absicht/notes/`, so a colleague can promote one.

- `ab note add [TEXT]` — body from the argument, stdin, or `--edit`; the id is
  generated (`note:a1b2c3`), never asked for
  - `--ref REF` optional anchor to an element
- `ab note list` — the inbox: unpromoted notes, with age surfaced
  ("14 notes, oldest 3 months"), not just a count
  - `--ref REF` `--all` (include promoted) `--format {text,json,ids}`
- `ab note show ID`
- `ab note promote ID KIND SLUG` — it became a question, decision, requirement
  or behavior: creates the element (same machinery as `ab new`), records
  `promoted_to` on the note, which removes it from the inbox
- `ab note drop ID` — it never mattered; deletes the file

### `ab check`

Validate the store. The core command — everything else assumes it passed.

Runs three layers: schema (fields, types, patterns), integrity (every ref
resolves, no cycles in `contains` or `depends_on`, criteria anchored to their
story), and policy (an `unknown` needs an owner, a requirement needs a
realizing component, a `one_way` decision needs a rationale body, an external's
assumptions have not expired).

The [model addendum](ABSICHT-MODEL-ADDENDUM.md) adds rules per layer: a seam
referencing a resource, an observation whose `at` does not resolve or points
at a requirement/decision/question, a `must_not` observation carrying
`timing`, composition and supersession cycles, a superseded behavior in a
milestone's must-satisfy set, and a note whose `promoted_to` does not resolve
are errors; a behavior with no observations is an error; a requirement with no
behavior realizing it is a warning.

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
A behavior's observations render one line each — statement, `at`, `outcome`
and the effective timing (the addendum's §1.2 default when the author said
nothing; none for `must_not`). A behavior also carries its derived facts —
`scope` (§4.1), `composes` / `composed_by` (§4.2) and `superseded_by` (§5) —
computed from the store, never stored in it, additive in `--json`; and a
superseded behavior is marked `[superseded]` wherever it appears.

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
- `--lifecycle {active,superseded}` behaviors only — the axis `state` is not
  (addendum §5); a usage error on a kind that has none
- `--scope {local,system}` behaviors only — the derived §4.1 classification,
  which is also the extra column a behavior's row carries; a usage error on
  a kind that has none
- `--format {text,json,ids}` `ids` for piping

An unowned element in state `unknown` groups under the owner of the single
element referencing it (addendum §7) — one level of inheritance, never
stored, so `--owner` and `--unowned` answer for inherited owners too.

### `ab gaps`

Everything unfinished, as a worklist: `unknown`, `observed`, `delegated`, open
questions, unowned elements, expired external assumptions, and behaviors with
no observations. An unowned `unknown` with exactly one referencing owner
reports that owner on its line, marked `(inherited)` — and as
`owner_inherited` in `--json` — instead of counting as unowned.

- `--kind KIND` `--owner WHO` `--overdue`
- `--blocking REF` only gaps that block this element or milestone
- `--format {text,json}`

### `ab trace REF`

Traceability paths through the graph: requirement to component to seam to
decision, in either direction.

Enumeration is bounded: a dense graph holds exponentially many simple paths,
so the walk carries a budget — 1000 paths, spent in deterministic walk order
— and says `truncated` in text and json when the answer was cut short rather
than complete (the mermaid diagram draws the paths it was given, silently).
The site's traceability page shows the first 50 per requirement and spells
its own cut.

- `--to REF` paths between two elements
- `--up` / `--down` direction. Default both
- `--format {text,json,mermaid}`

### `ab render`

Generate the read-only site: element pages, traceability, gaps, the note
inbox, diagrams.

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

Per the [model addendum §5](ABSICHT-MODEL-ADDENDUM.md#5-lifecycle-and-supersession),
the packet also carries two behavior lists: the behaviors this slice must
**satisfy** (the new work) and the active behaviors it must **not break**
(standing expectations touching the components in scope). Behavior composition
expands one hop — if A composes B and B composes C, a packet scoped to A
includes B's observations and references C without expanding it. Notes are
never packet input. Packet issuance is recorded in the local run store
(`(milestone, design rev, packet id, timestamp, target agent)`); the packet
artifact itself is deterministic from milestone plus design rev and is
regenerated rather than stored.

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
- `--target-agent WHO` who the packet is handed to; recorded with the
  issuance in the local run store

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

Per the [model addendum §9](ABSICHT-MODEL-ADDENDUM.md#9-what-verification-does-and-does-not-do),
verification also asks whether every `must` and `must_not` observation in the
packet **has something checking it**, and reports three outcomes per
observation: `checked` (something verifies it, with evidence), `no_check`
(nothing does — the observation is unguarded), `advisory` (it is a `should`;
reported, never failed). The unchecked-`should` count is surfaced as
visibility, not as an error. absicht does not run checks and does not own
assertions. Each run is recorded in the local run store
(`(packet id, commit sha, per-criterion result, evidence ref)`) — beside the
design store, never in git; a run where no design store can be located, the
fetched-packet CI case, prints a note and records nothing.

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

That is the reference-mode report. Embedded, design and code land in the same
commit and nothing can be behind, so what is left is implementation coverage and
unmet `done_when`.

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

- `ab extract --to URL` move `.absicht/` out to a new store repo and leave a
  populated `.absicht` file behind. This is the transition a hand-migration gets
  wrong — the marker has to name the right units and paths, and carry a
  watermark for the commit that split them — which is why it is a command
- `ab import --repo PATH` brownfield extraction: structure from code,
  everything intent-shaped lands as `observed` or `unknown`
- `ab mine --repo PATH` candidate decisions from git history, PRs and ADR
  folders, with provenance and confidence, for a human to accept or kill
- `ab serve` the webapp, once there is something worth looking at

## Notes

`--json` output is versioned and additive. Agents parse it, so a field never
changes meaning — it gets deprecated and a new one appears.

Where a command also has `--format` with a `json` member, an explicit `--format`
wins; `--json` selects json only when `--format` was left at its default. It is
a shorthand, never an override.

No command mutates the store as a side effect of reading. `check`, `build`,
`packet`, `verify` and `status` are all safe to run anywhere, any number of
times. The run history `packet` and `verify` append under `build/` is not
the store: it is never committed, and losing it loses history, not design.

No command in this list needs a network or an LLM.
