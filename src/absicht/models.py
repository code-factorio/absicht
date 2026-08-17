"""absicht — initial data model.

Rules this file tries to obey:

1. A field exists only if something computes over it. Everything else is prose
   in `body`.
2. `body` is the file body. It is never parsed, only carried and rendered.
3. References are typed strings, `kind:slug`. Identity carries no location, so
   moving or extracting an element never breaks a link.
4. Nothing here knows about files, YAML, HTTP or git. The codec puts records in,
   the resolver links them, everything downstream reads the built artifact.

Cross-element checks (does this ref resolve, is every requirement realized, is
anything Unknown without an owner) do not live here. They belong in `check.py`,
where a failure is a report line rather than an exception.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SCHEMA_VERSION = 1


# ---------------------------------------------------------------- primitives

Ref = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z]+:[a-z0-9][a-z0-9-]*$", strip_whitespace=True),
]
"""A typed identity: `component:cancellation`, `decision:event-log`.

The prefix names the kind, so a reference is checkable without a lookup and an
element can move between repos without breaking anything that points at it.
"""

CriterionId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z]+:[a-z0-9][a-z0-9-]*#ac-\d+$"),
]
"""A criterion, anchored to its parent: `story:cancel-order#ac-1`.

Globally unique, traceable to the story, and stable across rewording — so step
definitions written against it are not orphaned when the prose changes.
"""

ObservationId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z]+:[a-z0-9][a-z0-9-]*#obs-\d+$"),
]
"""An observation, anchored to its behavior: `behavior:new-chat-session#obs-2`.

Anchors to its behavior exactly as `CriterionId` anchors to its story:
verification results hang off the id, so it must survive rewording and stay
traceable to the behavior it observes.
"""

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]


class State(StrEnum):
    """How complete an element is, and what an agent may do about it."""

    SPECIFIED = "specified"  # implement as written; flag contradictions
    CONSTRAINED = "constrained"  # decide inside the guardrails, show reasoning
    DELEGATED = "delegated"  # decide, record the result
    UNKNOWN = "unknown"  # ask or spike; never invent
    OBSERVED = "observed"  # code does this, nobody knows why; ask
    OUT_OF_SCOPE = "out_of_scope"  # do not build; report scope leakage


class Confidence(StrEnum):
    """How much we trust this, independent of how complete it is."""

    ASSUMED = "assumed"  # nobody checked
    REVIEWED = "reviewed"  # a human agreed
    VERIFIED = "verified"  # evidence exists (test, measurement, contract)


class Reversibility(StrEnum):
    """Cost of being wrong. The delegation axis that actually matters."""

    CHEAP = "cheap"  # agent may decide freely
    COSTLY = "costly"  # agent proposes, human confirms
    ONE_WAY = "one_way"  # human decides


class Record(BaseModel):
    """Base config for everything. Frozen, strict, no silent extra keys."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
        use_attribute_docstrings=True,
    )


class Element(Record):
    """Common to every addressable thing in the design."""

    id: Ref
    title: str = Field(min_length=1)
    state: State = State.UNKNOWN
    confidence: Confidence = Confidence.ASSUMED
    owner: str | None = None
    tags: tuple[str, ...] = ()

    # provenance — set by the loader, not authored
    source: str = ""
    """Path within the store. Written by the loader."""
    body: str = ""
    """Prose, verbatim. Never parsed."""


# ------------------------------------------------------------------- system


class ExternalKind(StrEnum):
    SERVICE = "service"  # Stripe, an internal service we don't own
    RUNTIME = "runtime"  # Postgres, Redis, a queue
    LIBRARY = "library"  # a dependency we pull in


class External(Element):
    """Something we depend on and will never own the design of.

    We do own our assumptions about it, and when they expire.
    """

    external_kind: ExternalKind
    version: str | None = None  # what we assume: "2026-03", ">=16"
    assumptions: tuple[str, ...] = ()  # contract, semantics, failure modes
    verified_on: date | None = None
    verified_by: str | None = None
    expires_on: date | None = None  # after this, re-check before trusting

    @model_validator(mode="after")
    def _verified_before_expiry(self) -> External:
        if self.verified_on and self.expires_on and self.expires_on < self.verified_on:
            raise ValueError("expires_on is before verified_on")
        return self


class Unit(Record):
    """A design unit this system composes. Its own release cadence."""

    id: Ref
    design: str | None = None  # store URL, when the unit is external
    repo: str | None = None
    ref: str = "main"
    """A ref, never a pin. Pinning belongs to a deliberate upgrade."""


class System(Element):
    purpose: str = ""
    units: tuple[Unit, ...] = ()
    externals: tuple[Ref, ...] = ()


# ------------------------------------------------------------- requirements


class Requirement(Element):
    """Functional. What the system must do."""

    realized_by: tuple[Ref, ...] = ()  # components
    constrains: tuple[Ref, ...] = ()  # seams, data, components
    derived_from: tuple[Ref, ...] = ()  # other requirements, stories


class QualityAttribute(StrEnum):
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    AVAILABILITY = "availability"
    DURABILITY = "durability"
    SECURITY = "security"
    PRIVACY = "privacy"
    COST = "cost"
    OPERABILITY = "operability"


class NonFunctional(Element):
    """A quality attribute scenario. Prose targets are not checkable."""

    attribute: QualityAttribute
    scope: tuple[Ref, ...] = ()  # what it applies to
    stimulus: str = ""  # "1000 concurrent cancellations"
    measure: str = ""  # "p99 response time"
    target: str = ""  # "< 200ms"
    evidence: tuple[str, ...] = ()  # benchmark or probe, when it exists


# ------------------------------------------------------------------ stories


class CriterionKind(StrEnum):
    BEHAVIOURAL = "behavioural"  # renders to Gherkin
    STRUCTURAL = "structural"  # checked by ab verify
    MEASURED = "measured"  # checked by a benchmark or probe


class Criterion(Record):
    """Acceptance criterion. Behavioural ones serialize to a scenario.

    `id` is stable and survives rewording, so step definitions written against
    it are not orphaned when the story text changes.
    """

    id: CriterionId
    kind: CriterionKind = CriterionKind.BEHAVIOURAL
    given: tuple[str, ...] = ()
    when: str = ""
    then: tuple[str, ...] = ()
    statement: str = ""  # non-behavioural criteria use this instead
    touches: tuple[Ref, ...] = ()  # seams, components exercised

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> Criterion:
        if self.kind is CriterionKind.BEHAVIOURAL:
            if not self.when or not self.then:
                raise ValueError("a behavioural criterion needs `when` and `then`")
            if self.statement:
                raise ValueError("use given/when/then, not `statement`")
        elif not self.statement:
            raise ValueError(f"a {self.kind} criterion needs `statement`")
        return self


class Story(Element):
    actor: str = ""
    outcome: str = ""
    satisfies: tuple[Ref, ...] = ()  # requirements
    acceptance: tuple[Criterion, ...] = ()

    @model_validator(mode="after")
    def _criteria_anchored_to_story(self) -> Story:
        for c in self.acceptance:
            if c.id.split("#")[0] != self.id:
                raise ValueError(f"criterion {c.id!r} is not anchored to {self.id!r}")
        return self


# --------------------------------------------------------------- structure


class Component(Element):
    responsibility: str = ""
    contains: tuple[Ref, ...] = ()  # child components; C4 zoom is nesting
    consumes: tuple[Ref, ...] = ()  # seams, externals
    provides: tuple[Ref, ...] = ()  # seams
    owns_data: tuple[Ref, ...] = ()
    implemented_by: tuple[str, ...] = ()
    """"repo#path". The authoritative side of the link; markers are hints."""


class SeamStyle(StrEnum):
    CALL = "call"  # in-process interface
    HTTP = "http"
    EVENT = "event"
    QUEUE = "queue"
    SCHEMA = "schema"  # shared table, file format


class Seam(Element):
    """A boundary. The provider owns the contract; consumers own expectations."""

    style: SeamStyle
    provider: Ref | None = None
    consumers: tuple[Ref, ...] = ()
    contract: str = ""  # path or URL to the artifact, when one exists
    carries: tuple[Ref, ...] = ()  # data entities crossing it
    failure_modes: tuple[str, ...] = ()
    verified_by: tuple[str, ...] = ()  # contract tests


class FieldSpec(Record):
    name: Slug
    type: str
    optional: bool = False
    note: str = ""


class DataEntity(Element):
    owner_component: Ref | None = None
    fields: tuple[FieldSpec, ...] = ()
    identity: tuple[str, ...] = ()  # which fields identify an instance

    @model_validator(mode="after")
    def _identity_fields_exist(self) -> DataEntity:
        names = {f.name for f in self.fields}
        if missing := set(self.identity) - names:
            raise ValueError(f"identity names unknown fields: {sorted(missing)}")
        return self


# ---------------------------------------------------- resources and behaviors


class ResourceKind(StrEnum):
    """What an observation about the resource looks like, and how it is checked.

    The one axis a resource `kind` is allowed to carry (addendum §1.2) —
    something branches on each value, or the value does not exist. Anything
    merely descriptive belongs in `technology` or a tag; a fourth value is a
    spec change, not an edit here.
    """

    STORE = "store"  # something persists there; read what is there
    ENDPOINT = "endpoint"  # a call happened; intercept or log it
    STREAM = "stream"  # a message was emitted; consume and assert


class Resource(Element):
    """An addressable thing the system depends on but does not design.

    Forcing Redis or S3 to be a component would put it inside the design
    boundary: we do not specify them, we specify what we expect to find in
    them. Observations point here. Ownership needs no field of its own —
    `state` already answers it (`specified` we define, `delegated` another
    team owns, `out_of_scope` deliberately outside), so there is no
    `provided_by` (§1.3). And a resource takes part in no seam: a
    component's relationship to one is a dependency, and the observations
    referencing it are what give it meaning (§1.4).
    """

    resource_kind: ResourceKind
    technology: str = Field(min_length=1)
    """Free text, forever (§1.1): `Redis`, `Stripe API`, a filesystem path.

    The C4 refusal of a storage taxonomy, held as a string so it never needs
    migrating when next year's store arrives.
    """


class Outcome(StrEnum):
    """Whether an observation is required, forbidden, or advisory."""

    MUST = "must"  # required: something has to check it
    MUST_NOT = "must_not"  # forbidden: at no point
    SHOULD = "should"  # advisory: reported, never failed


class Timing(StrEnum):
    """When an observation's outcome becomes true."""

    IMMEDIATE = "immediate"  # checkable now: read the store, intercept the call
    EVENTUAL = "eventual"  # true only after propagation: consume and assert


class Observation(Record):
    """One expectation about how the system acts, anchored to its behavior.

    The counterpart of `Criterion`: a criterion says when a story is done,
    an observation says how you would know the system acted. `at` names what
    it points at — a component, a resource, a seam, or another behavior
    (composition); which of those are legitimate targets is `check`'s to
    say, not this file's.
    """

    id: ObservationId
    statement: str = Field(min_length=1)
    at: Ref
    outcome: Outcome = Outcome.MUST
    timing: Timing | None = None
    """Optional on purpose: the effective timing is computed, never defaulted
    here — an authored value wins, else the default follows what `at` points
    at (`effective_timing`). Storing a default would make "not said" and
    "deliberately immediate" indistinguishable."""

    @model_validator(mode="after")
    def _must_not_carries_no_timing(self) -> Observation:
        # `must_not` means "at no point"; a timing on it says when the never
        # happens. A shape the record cannot have is a parse-time failure,
        # like `Criterion._shape_matches_kind` (`schema/must-not-has-timing`).
        if self.outcome is Outcome.MUST_NOT and self.timing is not None:
            raise ValueError("`must_not` means at no point: omit `timing`")
        return self

    def effective_timing(self, resource_kind: ResourceKind | None) -> Timing:
        """The timing that governs, given the kind of what `at` resolved to.

        Lives on the record because `packet` and `verify` need the same
        answer and neither should re-derive the addendum §1.2 table: an
        authored value wins; a `stream` defaults `eventual`, a message being
        asserted by consuming it; everything else — `store`, `endpoint`, and
        any non-resource target — defaults `immediate`.
        """
        if self.timing is not None:
            return self.timing
        if resource_kind is ResourceKind.STREAM:
            return Timing.EVENTUAL
        return Timing.IMMEDIATE


class Lifecycle(StrEnum):
    """Whether an element is still how the system works.

    A second axis to `state`, which says how well specified it is: a
    behavior can be perfectly `specified` and no longer true.
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"


class Scope(StrEnum):
    """A behavior's reach, computed from its observations (§4.1).

    `local` — one component, no resources, no seams; `system` — anything
    else, including nothing observed anywhere. Never a field: the author
    states observations, the classification follows, so a behavior that
    grows an observation on a second component becomes a system behavior
    with no edit to say so. `absicht.resolve.scope_of` is the one spelling
    of the rule.
    """

    LOCAL = "local"
    SYSTEM = "system"


class Behavior(Element):
    """An expectation about how the system acts.

    The counterpart to a requirement: a requirement is what and why, a
    behavior is how you would know. Behaviors are permanent — not owned by
    a milestone, not expiring when one completes (§5). Supersession is
    recorded on the replacement (`supersedes`) and never mirrored as a
    stored `superseded_by`: same inversion as `parent` with no `children[]`.

    An empty `observations` tuple is valid here. A behavior mid-authoring is
    legitimate on disk; whether a finished one needs observations is
    `policy/behavior-needs-observations`'s report line, not an exception.
    """

    trigger: str = Field(min_length=1)
    """Prose — a sentence naming what happened. Not a condition, not Gherkin."""
    realizes: tuple[Ref, ...] = ()  # requirements this behavior is the how of
    lifecycle: Lifecycle = Lifecycle.ACTIVE
    supersedes: tuple[Ref, ...] = ()  # the behaviors this one replaces
    observations: tuple[Observation, ...] = ()  # inline, like a story's `acceptance`

    @model_validator(mode="after")
    def _observations_anchored_to_behavior(self) -> Behavior:
        # Mirrors `Story._criteria_anchored_to_story`: the id says which
        # behavior an observation belongs to, and a mismatch is a broken
        # file, not a design judgement.
        for observation in self.observations:
            if observation.id.split("#")[0] != self.id:
                raise ValueError(f"observation {observation.id!r} is not anchored to {self.id!r}")
        return self


class Note(Record):
    """A thought captured against the store — deliberately not an element.

    Not in `Design`, not in the resolved graph, never packet input: an agent
    never sees a note (addendum §6). Nothing is required beyond an id and a
    creation date — the moment authoring a note asks for classification it
    stops being used — so there is no title, state, owner or tags to ask
    for. If it matters to the work it gets promoted into a real element,
    which is what `promoted_to` records.
    """

    id: Ref
    ref: Ref | None = None  # what it was captured against, when obvious
    created: date
    promoted_to: Ref | None = None  # the element it became; set on promotion

    # provenance — `source` is set by the loader, not authored; `body` is the
    # note itself
    source: str = ""
    body: str = ""
    """The note. Markdown, never parsed."""


# --------------------------------------------------------------- decisions


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"


class Decision(Element):
    """ADR. Context and consequences live in `body` — the argument is the point."""

    status: DecisionStatus = DecisionStatus.PROPOSED
    decided_on: date | None = None
    reversibility: Reversibility = Reversibility.CHEAP
    applies_to: tuple[Ref, ...] = ()
    supersedes: tuple[Ref, ...] = ()


class Rejection(Element):
    """Tried it, it was bad. Stops agents re-proposing dead ideas."""

    applies_to: tuple[Ref, ...] = ()
    rejected_on: date | None = None
    milestone: Ref | None = None


class ResolutionMethod(StrEnum):
    ASK = "ask"
    SPIKE = "spike"
    PROTOTYPE = "prototype"
    MEASURE = "measure"


class Question(Element):
    """An `unknown` with an owner and a way out. Without those it is a wish."""

    method: ResolutionMethod = ResolutionMethod.ASK
    blocks: tuple[Ref, ...] = ()
    due_on: date | None = None
    resolved_by: Ref | None = None  # the decision that closed it


# -------------------------------------------------------------- milestones


class Milestone(Element):
    """A vertical slice. A selection over the model, plus the delta."""

    outcome: str = ""
    includes: tuple[Ref, ...] = ()  # stories, requirements
    scope: tuple[Ref, ...] = ()  # components, seams the agent may touch
    must_hold: tuple[Ref, ...] = ()  # ADRs, NFRs
    may_decide: tuple[str, ...] = ()  # explicit freedoms
    unresolved: tuple[Ref, ...] = ()  # questions knowingly left open
    done_when: tuple[CriterionId, ...] = ()
    depends_on: tuple[Ref, ...] = ()


# ------------------------------------------------------- implementation side


class UnitWatermark(Record):
    """From a repo's `.absicht` marker. A hint, not a proof.

    Tends to over-claim: a merge stamps it whether or not the work was finished.
    """

    id: Ref
    path: str = "."
    at: Ref | None = None  # last milestone landed here
    design_rev: str | None = None  # design head when it landed


class Marker(Record):
    """A repo's `.absicht` file. Discovery hint; the store stays authoritative."""

    design: str
    units: tuple[UnitWatermark, ...] = ()


# ------------------------------------------------------------- the artifact


class Design(Record):
    """The normalized build output. Deterministic, disposable, gitignored.

    Everything downstream — renderer, packet, verify, agents — reads this and
    nothing else.
    """

    schema_version: int = SCHEMA_VERSION
    system: System
    externals: tuple[External, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    non_functionals: tuple[NonFunctional, ...] = ()
    stories: tuple[Story, ...] = ()
    components: tuple[Component, ...] = ()
    seams: tuple[Seam, ...] = ()
    data: tuple[DataEntity, ...] = ()
    resources: tuple[Resource, ...] = ()
    behaviors: tuple[Behavior, ...] = ()
    decisions: tuple[Decision, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    questions: tuple[Question, ...] = ()
    milestones: tuple[Milestone, ...] = ()


# ------------------------------------------------------------------- layout


class Position(Record):
    """One diagram node's pinned coordinates: where `ab render` draws the box."""

    ref: Ref
    x: float
    y: float


class Layout(Record):
    """The `layout.yaml` singleton: one pinned position per diagram node.

    Positions are design data, not a rendering detail — `ab layout` computes
    them deterministically and pins them here, `ab render` reads them and
    never invents its own, so boxes do not move between builds. A tuple in
    id order like every other collection in this file: the dump's field
    order is the model's own, and byte-identical output needs that order to
    be data rather than dict insertion order.
    """

    positions: tuple[Position, ...] = ()


# ------------------------------------------------------------------- packet


class Fidelity(StrEnum):
    FULL = "full"  # in scope: everything
    CONTRACT = "contract"  # one ring out: the seam, nothing behind it


class PacketElement(Record):
    ref: Ref
    fidelity: Fidelity
    element: dict[str, object]  # the element, as built


class Packet(Record):
    """What an agent is handed. Bounded, self-contained, offline-verifiable."""

    schema_version: int = SCHEMA_VERSION
    milestone: Ref
    design_rev: str = ""
    outcome: str = ""
    elements: tuple[PacketElement, ...] = ()
    satisfy: tuple[Ref, ...] = ()
    """The behaviors this slice must newly satisfy — the new work. The
    behaviors themselves ride in ``elements`` at ``Fidelity.FULL``, one hop of
    composition expanded beside them (addendum §5, §4.2)."""
    must_not_break: tuple[Ref, ...] = ()
    """The active behaviors whose observations touch the milestone's scope —
    standing expectations, not new work. Breaking one is a regression; the
    mechanical form of "do not regress the rest of the system" (§5)."""
    must_hold: tuple[Ref, ...] = ()
    may_decide: tuple[str, ...] = ()
    unresolved: tuple[Ref, ...] = ()
    rejections: tuple[Ref, ...] = ()  # do not re-propose these
    criteria: tuple[Criterion, ...] = ()
    scenarios_digest: str = ""  # hash of the emitted .feature files


class PacketLock(Record):
    """The `packet.lock` sidecar: what a sealed packet was sealed against.

    Written beside the packet body by `ab packet --seal` and read back by
    `ab verify` — the only reader — so a verification can run offline, in CI,
    with no design store: the store commit the packet was built from
    (`design_rev`) and the digest of the rendered `.feature` files
    (`scenarios_digest`) are everything "handed over against this" means. Both
    ends go through this model, so the writer's and reader's spelling of the
    file cannot drift.
    """

    schema_version: int = SCHEMA_VERSION
    design_rev: str
    scenarios_digest: str
