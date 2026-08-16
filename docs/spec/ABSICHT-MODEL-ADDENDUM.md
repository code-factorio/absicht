# absicht — model addendum: behaviors, resources, notes

**Status:** Proposal · Nothing implemented · Date: 2026-08-16

Four additions to the model. Three are elements; one is deliberately not.

---

## 0. This is a model change, not a UI feature

These additions surfaced during UI design work. That is where they were *noticed*, not
where they live.

Everything below changes the schema, the validator, the CLI, the packet, and what an
agent receives. The browser is one projection of the model and the least important
consumer of it — roughly 95% of reads are machine reads, through `ab --json`, an MCP
server, or a skill teaching an agent to drive the CLI.

Concretely, each addition must land in all of:

| Surface | What changes |
|---|---|
| `model/` | msgspec structs, and therefore the generated JSON Schema |
| `check` | new validation rules, listed per section below |
| `packet` | behaviors are packet content; notes explicitly are not |
| `verify` | observations are what verification checks for |
| CLI | authoring commands, `--json` output shapes |
| Renderers | static site, served app, diagrams — last, not first |

A design that is only reachable through the browser is a defect. If an addition below
cannot be authored and read from the CLI, it is wrong.

---

## 1. Resource

An addressable thing the system depends on but does not design. Observations point at
it.

```yaml
id: resource:session-cache
kind: store
technology: Redis
state: observed
owner: platform
```

Without resources, an expectation like "a cache entry appears under `sess:{id}`" has
nowhere to land. Forcing Redis to be a component would put it inside the design
boundary, where it does not belong — we do not specify Redis, we specify what we
expect to find in it.

### 1.1 `technology` is free text, forever

`Redis`, `PostgreSQL`, `Kafka`, `S3`, `Stripe API`, `MongoDB`, a filesystem path.

This follows C4, which deliberately refuses a storage taxonomy: a container is "an
application or a data store", and the technology is a string. Every attempt to
enumerate storage technologies is a schema change waiting to happen — key-value,
relational, document, columnar, object, queue, stream, and whatever arrives next year.
A string never needs migrating.

ArchiMate is the counter-example and the warning: node, device, system software,
artifact, path, network — a complete taxonomy, organised around deployment and
hardware, which is not an axis absicht cares about.

### 1.2 `kind` is three values, and it is read

A `kind` earns its place only if something in absicht branches on it. The axis that
qualifies is **what an observation about it looks like, and therefore how it is
checked**.

| kind | An observation asserts | Checked by | Default timing |
|---|---|---|---|
| `store` | something persists there | reading what is there | `immediate` |
| `endpoint` | a call happened | intercepting or logging the call | `immediate` |
| `stream` | a message was emitted | consuming and asserting | `eventual` |

Redis, Postgres, Mongo, S3 and a filesystem are all `store`, differing only in
`technology`. Stripe, an internal REST service and a gRPC target are `endpoint`.
Kafka, SQS and an event bus are `stream`.

Anything merely descriptive goes in `technology` or a tag, never in `kind`.

### 1.3 Ownership needs no field

Whether we control a resource is already expressed by `state`: `specified` for
something we define, `delegated` for something another team owns, `out_of_scope` for
something deliberately outside. C4 resolves the same question the same way — you do
not run S3, but you own your buckets.

There is no `provided_by`.

### 1.4 Resources do not participate in seams

A seam is a contract between components. A component's relationship to a resource is a
dependency, and what gives it meaning is the observations referencing it, not a
contract we author.

**Check rule:** a seam referencing a resource is an error.

---

## 2. Behavior

An expectation about how the system acts. The counterpart to a requirement: a
requirement is *what and why*, a behavior is *how you would know*.

```yaml
id: behavior:new-chat-session
state: specified
lifecycle: active
trigger: A user starts a new chat session.
realizes: [req:session-persistence]
owner: platform
```

`trigger` is prose — a sentence naming what happened. Not a condition, not Gherkin.

Behaviors carry `state` like any element, which matters more than it first appears: an
import of a brownfield system produces `observed` behaviors (this is what the code
does), and a design in progress carries `unknown` ones (something happens here and we
have not said what).

Behaviors are permanent. They are not owned by a milestone and do not expire when one
completes — see §5.

**Check rules:** a behavior with no observations is an error. A requirement with no
behavior realizing it is a warning, not an error.

---

## 3. Observation

Anchored to its behavior, following the existing pattern for criteria
(`story:cancel-order#ac-1`):

```yaml
id: behavior:new-chat-session#obs-2
statement: Session state object is written
at: resource:state-store
outcome: must
timing: immediate
```

### 3.1 `outcome` carries polarity, `timing` carries when

| Field | Values | Meaning |
|---|---|---|
| `outcome` | `must` / `must_not` / `should` | Whether it is required, forbidden, or advisory |
| `timing` | `immediate` / `eventual` | When it becomes true |

Early drafts conflated these, using a `never` timing to express negation. Splitting
them is cleaner and it makes `must_not` say what it means: at no point. **`timing` is
omitted for `must_not`** and its presence is a check error.

**Negative observations are first-class.** "No entry appears in the audit log" is how
double-writes, leaks and unintended side effects get caught, and it is the kind of
expectation that never survives being written as prose.

**`should` is advisory and never fails verification.** It exists so weak expectations
can be recorded honestly rather than inflated into requirements. Verification reports
it as a separate class. The failure mode to watch is `should` becoming a dumping
ground, so the unchecked-`should` count is surfaced — as visibility, not as an error.

`timing` matters because with layered caches and horizontal scaling, immediate versus
eventual is the substance of the expectation, not a detail. Left in prose, it cannot be
checked.

### 3.2 `at` — what an observation can point at

A component, a resource, a seam, or another behavior.

Pointing at a **seam** says the expectation is about a call crossing that contract.
Pointing at a **behavior** is composition — see §4.

**Check rule:** `at` must resolve. An `at` pointing at a requirement, decision,
question or note is an error.

### 3.3 Worked example

```yaml
# behavior:new-chat-session
trigger: A user starts a new chat session.

observations:
  - statement: Cache entry exists under sess:{id}
    at: resource:session-cache
    outcome: must
    timing: immediate

  - statement: State object is written
    at: resource:state-store
    outcome: must
    timing: immediate

  - statement: Session appears in the user's session list
    at: component:chat-api
    outcome: must
    timing: eventual

  - statement: No entry is written to the audit log
    at: resource:audit-log
    outcome: must_not
```

Four observations across two resources and one component. Neither Gherkin nor prose
would carry this legibly.

---

## 4. Derived scope and composition

### 4.1 Scope is computed, never declared

The set of elements a behavior touches is the union of its observations' `at` refs.
Classification follows:

- **local** — one component, no resources, no seams
- **system** — anything else

Nothing is stored and the author never picks a level. Same discipline as `ready` and
epic status in Rohrpost: state the primitive, compute the structure. A behavior that
grows an observation on a second component becomes a system behavior with no edit to
say so.

### 4.2 Composition

An observation may assert that another behavior occurs:

```yaml
- statement: Cache warming is triggered
  at: behavior:warm-session-cache
  outcome: must
  timing: eventual
```

This makes behavior chains expressible, which is how real systems read — one thing
happening causes another. Without it, every expectation is an island and the chain
lives only in prose.

Two consequences, both cheap now and expensive later:

**Cycles are an error.** `ab check` already walks the graph for `blocked_by` and
`depends_on`; behavior composition joins that walk.

**The packet scope walk stops at one hop.** If A composes B and B composes C, a packet
scoped to A includes B's observations and *references* C without expanding it.
Unbounded expansion means a packet silently grows to include half the system, which
defeats the point of bounding the work.

---

## 5. Lifecycle and supersession

`state` says how well-specified an element is. It cannot also say whether the element
is still true. A behavior can be perfectly `specified` and no longer how the system
works.

So behaviors carry a second axis:

```yaml
lifecycle: active        # active | superseded
```

with supersession recorded on the replacement:

```yaml
id: behavior:new-chat-session-v2
supersedes: [behavior:new-chat-session]
```

`superseded_by` is **derived**, never stored on both sides. Same inversion rule as
`parent` with no `children[]`: reverse edges mean every edit writes two files, and two
branches adding them conflict on a file neither is touching.

A superseded behavior is not deleted. It remains the record of what was expected
before, which is a large part of why a design store is worth keeping. It stops being
packet input and stops being verified.

**Milestone membership does not make a behavior live.** A behavior is a standing
expectation of the system, permanent until superseded. A milestone selects which
behaviors a slice must *newly satisfy*. This changes what a packet contains:

- Behaviors this slice must **satisfy** — the new work
- Behaviors it must **not break** — standing expectations touching the components in
  scope

The second list did not exist before this addendum and is the more valuable of the two.
It is the mechanical form of "do not regress the rest of the system", which is
otherwise left to an agent's judgement.

**Check rules:** `supersedes` must resolve; a behavior may not supersede itself;
supersession chains may not cycle. A `superseded` behavior appearing in a milestone's
must-satisfy set is an error.

---

## 6. Note

**Not an element.** Notes are not in the resolved graph, carry no state, are referenced
by nothing, and — the rule that keeps them from corroding the model —

> **Notes are never packet input. An agent never sees a note.**

```yaml
id: note:a1b2c3
ref: component:packet-builder     # optional
created: 2026-08-16
promoted_to: question:retention   # set on promotion
```

Body is Markdown. No kind, no owner, no parent, nothing required beyond an id.
**Capture friction must be near zero.** The moment authoring a note asks for
classification it stops being used and the thinking goes back to a scratch file, which
is the outcome this element exists to prevent.

Terminal states are **promoted** — it became a question, decision, requirement or
behavior — or **dropped**. Promotion records what it became and removes it from the
inbox. Age is surfaced, not just count: "14 notes, oldest 3 months" is useful pressure;
a bare count is not.

If something matters to the work it has to be promoted into a real element. A note that
is never promoted never mattered, and can be dropped without loss.

**Notes are committed.** They live in `.absicht/notes/` and are part of the design repo.
The consequence — half-formed thinking appears in diffs and pull requests — is accepted,
because a note a colleague can promote is worth more than a private scratchpad.

**Check rule:** `promoted_to` must resolve when present. Notes are otherwise exempt from
graph validation by construction.

---

## 7. `owner` on every element

Currently only `Question` carries an owner. Grouping unknowns by owner across
components, seams and requirements is a core query and the model cannot support it.

**Optional `owner` on every element**, as a free-text handle. Not a team model, not a
permissions system, not tied to git identity — a string for grouping.

**Unknowns inherit the owner of the element they sit on**, unless overridden. One level
of inheritance, no deeper. This is what makes ownership work without annotating every
field.

This is the only social field in the model and it stays free text until something needs
it not to be. Access control, review policy and approval belong to git hosting, not
here.

---

## 8. Where packets and verification runs live

**Not in git.**

They are machine-generated, produced per run, appended rather than authored, and never
reviewed as a diff. Committing them adds volume proportional to agent activity for no
benefit — the same argument that put bus state in SQLite rather than in the repository.

A local store beside the design store records two things:

- **Packet issued** — `(milestone, design rev, packet id, timestamp, target agent)`.
  The packet artifact itself is deterministic from milestone plus design rev, so it is
  regenerated rather than stored.
- **Verification run** — `(packet id, commit sha, per-criterion result, evidence ref)`.

Losing this store loses run history, not design. Recoverable but expensive, and
re-derivable by re-running.

Exported packet YAML handed to an agent is an artifact, not a stored object. It belongs
in CI artifacts if anywhere.

---

## 9. What verification does and does not do

Verification asks whether every `must` and `must_not` observation **has something
checking it** — a test, an assertion, a metric, a log query — and reports three
outcomes:

| Result | Meaning |
|---|---|
| `checked` | Something verifies this observation, with evidence |
| `no_check` | Nothing verifies it — the observation is unguarded |
| `advisory` | It is a `should`; reported, never failed |

`no_check` is the distinctive result and the reason this is not a test framework.
absicht does not run checks and does not own assertions. The moment it does, it is a
BDD tool with a design store attached, which is a different and much larger product.

---

## 10. Open questions

1. **Does the one-hop packet expansion limit hold?** It is a guess. Real chains will
   say whether one hop is too shallow.
2. **Should `lifecycle` apply to elements other than behaviors?** Decisions already have
   `supersedes`. Requirements plausibly want the same. Deliberately not generalised yet.
3. **Do observations need an evidence hint** — a pointer to where a check would live —
   or does that couple the design to a repo layout?
4. **Is `stream` distinct enough from `store`?** An event log is arguably both. If the
   timing default is the only thing that differs, two kinds may be enough.
5. **How are behaviors imported from a brownfield codebase?** They arrive as `observed`,
   but nothing yet says what generates them.
