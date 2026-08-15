# absicht

> The design truth of a system, as files. What the code can never tell you.

`absicht` holds the part of a software system that does not survive in the
source: why it is shaped this way, what it must not do, what was deliberately
left open, and who is allowed to decide the rest. Structure is derivable from
code. Intent is not. This is a store for the part that is not.

The unit of output is the **packet** — a bounded, machine-readable brief for one
slice of work, assembled by walking the model. A human or a coding agent can act
on a packet without reading the whole system and without guessing at the parts
that were never written down.

## Why

A working system's design currently lives across Markdown scattered in repos,
diagrams in a browser tab, ADR folders nobody re-reads, tickets, slide decks and
a dozen dead LLM chats. None of it is queryable, none of it is linked, and none
of it survives contact with the next person or the next agent.

Agents made this expensive. They read code well and infer intent badly. Handing
one a repo and a sentence produces plausible work that violates constraints
nobody wrote down. The missing input is not more context — it is *bounded*
context: this scope, these contracts, these rules that must hold, these choices
you may make freely, these things we genuinely have not decided.

## Shape

Files in a repo, validated, rendered, queried. The tree below is the embedded
case, the store sitting in the repo it describes. It can also live in a repo of
its own; see [Discovery and watermarks](#discovery-and-watermarks).

```
.absicht/
├── system.yaml           # the system, its external dependencies, pinned
├── requirements/         # functional and non-functional, with rationale
├── stories/              # outcomes and acceptance criteria
├── components/           # responsibilities, ownership, state, source refs
├── seams/                # boundaries: contracts, models, failure modes
├── data/                 # entities, schemas, ownership, versioning
├── decisions/            # ADRs, and what was tried and rejected
├── milestones/           # vertical slices: selection over the model
└── layout.yaml           # pinned diagram positions
```

Records are structured. Prose exists only where reasoning cannot be reduced to
fields — ADR context, NFR rationale, rejections — and lives in the body of the
file so it diffs, reviews and merges like text.

`ab build` folds the tree into one normalized JSON document. Everything
downstream — validator, renderer, packet generator, agents — consumes that
artifact and nothing else. It is deterministic, schema-versioned, and
disposable.

## Deliberate gaps

Incompleteness is a state, not an omission. Every element declares one:

| State | Meaning | Agent posture |
| --- | --- | --- |
| `specified` | Decided and complete for this scope | Implement as written; flag contradictions |
| `constrained` | Boundary fixed, latitude inside it | Choose within the guardrails, show reasoning |
| `delegated` | Assigned elsewhere on purpose | Decide, record the result, raise an ADR if it matters |
| `unknown` | Information or judgement is missing | Ask, spike, or mark blocking. Never invent |
| `observed` | The code does this; nobody knows why | Do not implement, do not remove, ask |
| `out_of_scope` | Excluded from this boundary | Do not build. Report scope leakage |

`observed` is the brownfield state and the reason import works at all. A real
system arrives mostly amber. That is an honest reading, not a failed one — the
model fills in along the path of actual work, not through a backfill project
that never finishes.

## Multi-repo by default

Real products are composites: a monolith here, a shared library there, three
services and five vendors. A design unit is anything with its own release
cadence, not anything with its own deployment. `system.yaml` pins the units it
composes, like a lockfile, and a change to a dependency's *contract* shows up as
a diff instead of an outage.

External dependencies are first-class. We will never own Stripe's design truth,
but we own our assumptions about it — assumed contract, assumed failure modes,
who verified them, and when they expire.

Identity is stable and carries no location. Components get extracted from
monoliths into libraries into services; the ID survives the move.

## Discovery and watermarks

`.absicht` is overloaded by filesystem type, and the type is the mode:

- **`.absicht/`, a directory** — embedded. The store lives in this repo, next to
  the code it describes. The single-repo case.
- **`.absicht`, a file** — reference. The design lives in its own repo. The file
  is a discovery hint: where the store is, which units this repo implements, and
  a watermark per unit.
- **Neither** — not an absicht repo.

One `stat` distinguishes them, and one name is one directory entry, so the two
cannot both be present. This is how projects actually grow: start single-repo
with the design beside the code and no ceremony, and when a component gets
extracted into a repo of its own, the store moves out and a marker is left
behind. Same layout, no migration.

In reference mode the marker is what an agent dropped into an implementing repo
reads to find its design without being told where to look:

```yaml
# .absicht
design: https://github.com/org/system-design
units:
  - id: component:cancellation
    path: src/cancellation/
    at: M003             # last milestone landed here
    design_rev: a3f2c9   # design head at the time it landed
  - id: component:policy
    path: src/policy/
    at: M002
    design_rev: 71bd04
```

The marker is a discovery hint, never authority. The design repo owns
composition and implementation references; `ab check` verifies the two agree and
treats a mismatch as an error. Markers can be regenerated. They are optional —
public library with private design, or a vendor repo we cannot write to, both
have to work.

`design_rev` is a **watermark, not a pin**. It records where the code caught up
to, so drift becomes the signal rather than the failure: the diff between the
watermark and design head is the outstanding work, expressed as the ADRs,
constraints and seam changes this code has never seen. `at` answers the same
question for humans, in milestones. A runner bumps both in the commit that lands
the work — evidence, produced by the thing that produced the change.

Across a composite this is what `ab status` computes: which units are behind,
how far, and whether a seam moved underneath a consumer that has not caught up.

Watermarks are a reference-mode concern only. Embedded, design and code move in
the same commit, so nothing can be behind; `ab status` there reports
implementation coverage and unmet `done_when` instead of drift.

A watermark is a hint about where to look, not proof of conformance. Merged code
is not correct code. `at: M003` means someone shipped something claiming to be
M003, and nothing more.

## Where this sits

- **[rohrpost](https://github.com/code-factorio/rohrpost)** holds work. A ticket
  whose body is a packet is a different quality of input to a runner.
- **[vermittlung](https://github.com/code-factorio/vermittlung)** holds
  interpretation of the outside world. Many of its escalations are unclear
  precisely because deciding requires intent — bug or feature, permitted or
  forbidden, ours or theirs.
- `absicht` holds why.

Vermittlung decides what deserves attention. `absicht` says what is true and
what is permitted. Rohrpost holds what is being done about it. Each runs alone;
none is a plugin of the others.

## Status

Nothing is built. This document is the argument, not a description.

| Step | Contents | State |
| --- | --- | --- |
| **0** | Hand-written packets for three real slices; measure agent output against them | next |
| **1** | Schema, file layout, `ab check` — link integrity, orphans, ungoverned elements | after 0 |
| **2** | `ab build` and a generated read-only site: pages, traceability, gaps, stable-layout SVG | |
| **3** | Milestones as selections; `ab packet` with a one-ring context horizon | |
| **4** | Source correlation: `.absicht` markers, watermarks, seam contract tests, `ab status` in CI | |
| **later** | Brownfield extraction, decision mining from git history, drag-to-reposition | |

Step 0 is the falsification. If a hand-written packet does not measurably
improve what an agent produces, the rest of this is decoration and the project
should stop there.

## Not this

No ticket system — that is Rohrpost. No canvas or diagramming suite; diagrams
are generated projections and navigation aids. No editor before step 4, and
possibly never beyond dragging boxes. No required LLM: authoring, validation,
rendering, planning and packets all work without one. No claim that the model
proves the code. No round-trip sync with every provider. Not a product looking
for a market — a tool its author needs on Monday.

## Open questions

- What is the smallest schema that still produces a useful packet?
- What is the right context horizon — selected scope plus one ring of contracts,
  or something else?
- Files-first or server-first once several systems and several people are
  involved, and how does that survive an org boundary?
- When does a delegated choice have to come back as an ADR?
- What evidence promotes an element from tentative to stable?
- How much design truth can be mined from git history before a human has to
  confirm it?

## License

MIT © code-factorio
