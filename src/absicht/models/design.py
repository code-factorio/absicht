"""Proposed types for a design: intent, requirements, architecture, and gaps.

Rules this proposal obeys, taken from `absicht.models`:

1. A field exists only if something computes over it. Everything else is prose
   in `body`.
2. Identity is a typed string, `kind:slug`. A reference names its own kind, so
   it is checkable without a lookup and an element can move without breaking a
   link.
3. A validator here rejects a shape the record cannot have. Cross-element rules
   (does this ref resolve, is every requirement covered) belong in a checker,
   where a failure is a report line and not an exception.
4. An agent is the main reader. Every element therefore says how complete it
   is, how much we trust it, and what the agent may decide alone.
5. `Design` is built, never authored. The store is many files, one directory
   per kind, and each element's file owns its outgoing relationships; `codec`
   and `load` assemble this record from them. Nothing here knows about files,
   YAML or git.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

FORMAT_VERSION = 1


# ---------------------------------------------------------------- primitives

Ref = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z]+:[a-z0-9][a-z0-9-]*$", strip_whitespace=True),
]
"""A typed identity: `req:cancel-order`, `constraint:gdpr-erasure`."""

ObservationId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z]+:[a-z0-9][a-z0-9-]*#obs-\d+$"),
]
"""An observation, anchored to its behavior: `behavior:click-abc#obs-1`.

A test binds to this id, so the id must survive every rewording.
"""

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]

EXPORTABLE = frozenset({"interface", "term", "data"})
"""The kinds that may cross a design boundary: the contract, and nothing else.

A goal or a requirement is why we built the thing, and a component is the
thing. A consumer that points at either depends on our reasoning or on our
insides, which is the leakage a seam exists to prevent — so a design offers
its interfaces, the data that crosses them, and the words they use, and is
otherwise opaque. To name the whole system, a consumer uses the `design:` id
it already imported.
"""


class State(StrEnum):
    """How complete an element is, and what an agent may do about it.

    This is the field that lets a gap be deliberate. `specified` and
    `unknown` are both legal, and they instruct the agent differently, so
    silence never has to stand for either one.
    """

    SPECIFIED = "specified"  # implement as written; flag contradictions
    CONSTRAINED = "constrained"  # decide inside the guardrails, show reasoning
    DELEGATED = "delegated"  # decide, and record the result here
    UNKNOWN = "unknown"  # ask or spike; never invent
    OBSERVED = "observed"  # the code does this, nobody knows why; ask
    OUT_OF_SCOPE = "out_of_scope"  # do not build; report scope leakage


class Confidence(StrEnum):
    """How much we trust this, independent of how complete it is."""

    ASSUMED = "assumed"  # nobody checked
    REVIEWED = "reviewed"  # a human agreed
    VERIFIED = "verified"  # evidence exists: a test, a measurement, a contract


class Reversibility(StrEnum):
    """The cost of being wrong. It sets how far an agent may go alone."""

    CHEAP = "cheap"  # the agent may decide freely
    COSTLY = "costly"  # the agent proposes, a human confirms
    ONE_WAY = "one_way"  # a human decides


class Lifecycle(StrEnum):
    """Whether an element is still how the system works.

    A second axis to `state`, which says how well specified it is: an
    interface can be perfectly `specified` and no longer true.
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"


class Priority(StrEnum):
    """How strong the statement is, matching the modal verb it already uses.

    MoSCoW without the W: "won't have this time" is a plan, and the design
    holds no plans. Something we will not build is `state: out_of_scope`,
    which says it once.
    """

    MUST = "must"
    SHOULD = "should"
    COULD = "could"


class RelationshipType(StrEnum):
    """The edge kinds a checker branches on. Add one only if it does.

    The architecture side owns the trace: a component says which requirement
    it implements, never the reverse. The architecture changes more often, so
    the edge moves with the side that moves.
    """

    RELATES_TO = "relates_to"  # weakest edge; carries no rule

    # architecture -> intent
    IMPLEMENTS = "implements"  # component -> requirement, interface
    SATISFIES = "satisfies"  # component -> quality requirement
    CONSTRAINED_BY = "constrained_by"  # component -> constraint
    REALIZES = "realizes"  # behavior -> requirement
    # architecture -> architecture
    CALLS = "calls"  # component -> component, external service
    DEPENDS_ON = "depends_on"  # component -> library; also order

    # design -> design
    SPECIFIES = "specifies"  # design -> element, across an import
    DERIVES_FROM = "derives_from"  # child requirement -> parent, or -> goal
    REFINES = "refines"  # more detail, same intent
    CONFLICTS_WITH = "conflicts_with"  # both cannot hold; a checker reports it


# ------------------------------------------------------------------- records


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
    """`unknown` by default, so an element nobody finished never reads as
    settled. Saying nothing and saying "implement as written" must differ."""
    confidence: Confidence = Confidence.ASSUMED
    reversibility: Reversibility | None = None
    """Set it where the agent decides. `check` warns on a `constrained` or
    `delegated` element without one: the agent cannot judge how far to go."""
    lifecycle: Lifecycle = Lifecycle.ACTIVE
    supersedes: tuple[Ref, ...] = ()
    """Recorded on the replacement only. A stored `superseded_by` would be a
    second copy of one fact, and the two would disagree."""
    owner: str | None = None
    tags: tuple[str, ...] = ()

    # provenance — written by the loader, not authored
    source: str = ""
    """Path within the store."""
    body: str = ""
    """Prose, verbatim. Never parsed."""


class Relationship(Record):
    """An edge between two elements, kept out of both.

    A field carries a link with exactly one owner (`Interface.declared_by`,
    `Component.parent`). Everything many-to-many lives here, in one list,
    so two elements can never disagree about the same link.
    """

    source_id: Ref
    target_id: Ref
    type: RelationshipType
    description: str | None = None
    """The C4 arrow label: "sends orders to"."""
    technology: str = ""
    """The C4 arrow technology: "HTTPS/JSON". Free text, forever."""

    @model_validator(mode="after")
    def _no_self_edge(self) -> Relationship:
        if self.source_id == self.target_id:
            raise ValueError(f"{self.source_id!r} points at itself")
        return self


# ------------------------------------------------------------------ language


class Term(Element):
    """One word of the glossary. The design uses it and nothing else."""

    definition: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    """The other words people say for this one, so a reader who knows the
    wrong one still finds the right entry."""


class ActorKind(StrEnum):
    PERSON = "person"  # a role, never a named individual
    SYSTEM = "system"  # another system that calls or is called
    TIME = "time"  # a schedule that starts work


class Actor(Element):
    """Who or what the system serves, or is served by."""

    actor_kind: ActorKind = ActorKind.PERSON
    goals: tuple[str, ...] = ()


# -------------------------------------------------------------- requirements


class Goal(Element):
    """A business outcome. The why above the requirements.

    One goal answers the "so that" of twenty requirements, and it answers it
    once. A story sentence spreads the same intent over twenty slightly
    different wordings, and none of them can be checked.
    """

    outcome: str = Field(min_length=1)  # "Refunds cost half as much to handle"
    measure: str = ""  # "cost per refund"
    target: str = ""  # "< 2 EUR"
    """A goal with no measure is a slogan. `check` warns, and it is right."""
    stakeholders: tuple[Ref, ...] = ()  # actors
    horizon: date | None = None


class Requirement(Element):
    """Functional. What the system must do, and why.

    The three parts of "As an X, I want Y, so that Z" all live here or next
    door: X is `actors`, Y is `statement`, Z is the `Goal` this derives from.
    The sentence is therefore a rendering, and no second list of stories has
    to be kept in step with this one.
    """

    statement: str = Field(min_length=1)
    """One sentence, one requirement, with a modal verb that matches `priority`."""
    rationale: str = ""
    """Why, in prose. The measurable part belongs in the `Goal`."""
    priority: Priority = Priority.MUST
    actors: tuple[Ref, ...] = ()


class QualityAttribute(StrEnum):
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    AVAILABILITY = "availability"
    DURABILITY = "durability"
    SECURITY = "security"
    PRIVACY = "privacy"
    USABILITY = "usability"
    COST = "cost"
    OPERABILITY = "operability"


class QualityRequirement(Element):
    """Non-functional, as a scenario. A prose target is not checkable.

    `scope` may point at a behavior, and that is how a promise about how the
    system acts becomes measurable. "Both parts start without waiting" is an
    observation; "the pair finishes within 200 ms" is this. `priority` then
    separates a hard rule (`must`) from best effort (`should`).
    """

    attribute: QualityAttribute
    stimulus: str = ""  # "1000 concurrent cancellations"
    measure: str = ""  # "p99 response time"
    target: str = ""  # "< 200 ms"
    scope: tuple[Ref, ...] = ()  # components, interfaces, behaviors
    priority: Priority = Priority.MUST
    evidence: tuple[str, ...] = ()  # benchmark or probe, when one exists


# --------------------------------------------------------------- behaviours


class Outcome(StrEnum):
    """Whether an observation is required, forbidden, or advisory."""

    MUST = "must"  # required: something has to check it
    MUST_NOT = "must_not"  # forbidden: at no point
    SHOULD = "should"  # advisory: reported, never failed


class Timing(StrEnum):
    """When the outcome becomes true."""

    IMMEDIATE = "immediate"  # checkable now
    EVENTUAL = "eventual"  # true only after it propagates


class Observation(Record):
    """One expectation about how the system acts, anchored to its behavior.

    A negative observation is the reason this type exists. "No row appears in
    the audit log" catches the double write, the leak and the side effect
    nobody wanted, and it never survives being written as prose.
    """

    id: ObservationId
    statement: str = Field(min_length=1)
    at: Ref
    """A component, an interface, a resource, or another behavior. `check`
    says which targets are legal; a dangling `at` is a report line, not an
    exception."""
    outcome: Outcome = Outcome.MUST
    timing: Timing | None = None
    """Optional on purpose: the effective timing is computed, never stored,
    so "not said" and "deliberately immediate" stay different."""

    @model_validator(mode="after")
    def _must_not_carries_no_timing(self) -> Observation:
        if self.outcome is Outcome.MUST_NOT and self.timing is not None:
            raise ValueError("`must_not` means at no point: omit `timing`")
        return self

    def effective_timing(self, resource_kind: ResourceKind | None) -> Timing:
        """The timing that governs, given what `at` resolved to.

        The one spelling of the rule, because `packet` and `verify` both
        need the answer: an authored value wins, a stream is eventual
        because you assert it by consuming, everything else is immediate.
        """
        if self.timing is not None:
            return self.timing
        if resource_kind is ResourceKind.STREAM:
            return Timing.EVENTUAL
        return Timing.IMMEDIATE


class Behavior(Element):
    """What the system does when something happens.

    Permanent, and owned by no milestone. An import of an undocumented system
    produces behaviors in state `observed` and no requirement behind them — a
    legal state, and an honest one. A `realizes` edge links a behavior to the
    requirement that asked for it, where one asked.
    """

    trigger: str = Field(min_length=1)  # "The user clicks button ABC."
    """Prose. A sentence that names what happened, not a condition."""
    observations: tuple[Observation, ...] = ()

    @model_validator(mode="after")
    def _observations_anchored(self) -> Behavior:
        for o in self.observations:
            if o.id.split("#")[0] != self.id:
                raise ValueError(f"observation {o.id!r} is not anchored to {self.id!r}")
        return self


class ConstraintKind(StrEnum):
    """Where the constraint comes from. You did not choose it."""

    REGULATORY = "regulatory"
    TECHNICAL = "technical"
    ORGANISATIONAL = "organisational"
    COMMERCIAL = "commercial"


class Constraint(Element):
    """A limit the design must obey. A requirement you cannot trade away.

    What it binds is a `constrained_by` edge, not a field here: the edge
    carries the reason alongside the link, and one place cannot disagree
    with itself.
    """

    statement: str = Field(min_length=1)
    constraint_kind: ConstraintKind
    imposed_by: str = ""  # the law, the contract, the platform


# ------------------------------------------------------------------ boundary


class InterfaceStyle(StrEnum):
    CALL = "call"  # in-process
    HTTP = "http"
    EVENT = "event"
    QUEUE = "queue"
    FILE = "file"
    UI = "ui"


class Operation(Record):
    """One call an interface offers. The shape only, never the body."""

    name: Slug
    signature: str = ""
    """Free text: `charge(amount: Money) -> ChargeId`. A parameter model here
    would be a second type system, and it would always trail the real one."""
    idempotent: bool | None = None
    """`None` says nobody decided. A retry policy needs the answer."""
    errors: tuple[str, ...] = ()


class Interface(Element):
    """A seam. One element declares the contract, and hides what is behind it.

    Ousterhout's sense of the word: the value of an interface is the ratio
    between what it hides and what it shows. So a deep one names few
    operations and holds a lot; a long list of operations is the smell, not
    the achievement.

    `declared_by` is the owner, and it is not always the element that answers
    the call: an external service declares what we call, but a port inside a
    container is declared by the component that needs it, and satisfied by
    an adapter. Whoever declares it owns the shape.

    An interface on an external service is the part we require, written down
    as we understand it — the only version we can check against.

    This is also the lowest zoom, in place of a code model: a `call`
    interface declared by a level-3 component is the port. It names the shape
    and no class, so any type of that shape satisfies it, and the model does
    not rot each time somebody renames a class.
    """

    style: InterfaceStyle
    declared_by: Ref | None = None
    """The single owner of the shape. Components carry no `provides` list."""
    contract: str = ""
    """Path or URL of the artifact (OpenAPI, schema), when one exists."""
    operations: tuple[Operation, ...] = ()
    """Author these only where the shape is the design. An OpenAPI file in
    `contract` already carries them, and two copies disagree."""
    implemented_by: tuple[str, ...] = ()
    """"repo#path". A duck-typed shape declares nothing in the code, so the
    link back has to live here."""
    failure_modes: tuple[str, ...] = ()


# ------------------------------------------------------------- architecture


class ComponentLevel(StrEnum):
    """The C4 zoom. One type, one field — the fields do not change per level."""

    SYSTEM = "system"  # C4 L1: the boundary of what we design
    CONTAINER = "container"  # C4 L2: a thing we deploy or run
    COMPONENT = "component"  # C4 L3: a part inside a container


class Component(Element):
    """A part of the system we design. Nesting is the zoom, not a new type.

    A deep module, in the same sense as `Interface`: what it holds is the
    value, and what it shows is the cost. Its interfaces are the whole
    surface, and the children behind them are nobody else's business — a
    component with many interfaces is shallow, whatever its size.

    C4 level 4 is absent on purpose: the code is the truth, and a model of
    it goes stale within a week.
    """

    level: ComponentLevel
    responsibility: str = ""
    technology: str = ""
    """Free text, forever: `Python 3.13`, `React`. An enum needs migrating."""
    parent: Ref | None = None
    """One owner, so a part cannot sit in two containers. `check` holds the
    level rule: a container's parent is a system, a component's parent is a
    container, a system has none."""
    implemented_by: tuple[str, ...] = ()
    """"repo#path". The authoritative link to code; markers are hints."""


class Library(Element):
    """Code compiled into a container. It crosses no runtime boundary.

    C4 draws no libraries, and that is right — a library provides no
    interface and takes part in no call. The license and the version are
    still facts about the system, so the type exists.
    """

    package: str = Field(min_length=1)  # "pydantic", "org.slf4j:slf4j-api"
    ecosystem: str = Field(min_length=1)  # "pypi", "maven", "npm"
    version_range: str = ""
    """What we assume, never a pin. Pinning belongs to a deliberate upgrade."""
    license: str = ""
    replaceable: bool = True
    """`False` marks lock-in: the design would change if this one went away."""


class ExternalService(Element):
    """A system another party owns. We call it and never design it.

    It is the box beside our own: `Component` means a part we design, so a
    foreign system cannot be one without making that sentence false.

    Two cases. Where the other side has an absicht design, `design` names
    the import, and the interfaces we call are its exports — we hold no
    opinion of our own about a contract somebody else publishes. Where it
    has none, like Stripe, we write the `Interface` we require and own the
    assumptions behind it, with the date they expire.
    """

    design: Ref | None = None
    """The imported design that describes it. Must match an `Import.id`."""
    technology: str = ""  # "REST/JSON", "gRPC"
    contract: str = ""  # URL of the OpenAPI or the vendor docs
    assumptions: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    verified_on: date | None = None
    expires_on: date | None = None

    @model_validator(mode="after")
    def _verified_before_expiry(self) -> ExternalService:
        if self.verified_on and self.expires_on and self.expires_on < self.verified_on:
            raise ValueError("expires_on is before verified_on")
        return self


class ResourceKind(StrEnum):
    """What an observation about it looks like, and therefore how it is checked.

    Two values, because two things branch. A call is neither: an
    `ExternalService` is the system, an `Interface` is the call, and an
    observation about one points there.
    """

    STORE = "store"  # something persists; read what is there
    STREAM = "stream"  # a message was emitted; consume and assert


class Resource(Element):
    """An addressable thing we depend on but do not design.

    Redis and S3 are not components: we do not specify them, we specify what
    we expect to find in them, so making one a component would drag it
    inside the design boundary. Observations point here. Ownership needs no
    field, because `state` answers it — `specified` we define, `delegated`
    another team owns, `out_of_scope` deliberately outside. A resource takes
    part in no interface: a component's relation to one is a dependency, and
    the observations are what give it meaning.
    """

    resource_kind: ResourceKind
    technology: str = Field(min_length=1)
    """Free text, forever: `Redis`, `Kafka`, a filesystem path. C4 refuses a
    storage taxonomy for the same reason — a string never needs migrating."""


class FieldSpec(Record):
    name: Slug
    type: str
    optional: bool = False
    note: str = ""


class DataEntity(Element):
    """A thing the system stores or carries, and the component that owns it.

    `type` is free text and will trail the real type. The entity earns its
    place anyway: an agent asks who owns a table before it writes to one,
    and no other element answers that.
    """

    owner_component: Ref | None = None
    fields: tuple[FieldSpec, ...] = ()
    identity: tuple[str, ...] = ()  # which fields identify an instance

    @model_validator(mode="after")
    def _identity_fields_exist(self) -> DataEntity:
        names = {f.name for f in self.fields}
        if missing := set(self.identity) - names:
            raise ValueError(f"identity names unknown fields: {sorted(missing)}")
        return self


# --------------------------------------------------------- what we do not know


class Assumption(Element):
    """Something taken as true without proof. It expires."""

    statement: str = Field(min_length=1)
    verified_on: date | None = None
    expires_on: date | None = None
    """After this date, check it again before you trust it."""
    invalidates: tuple[Ref, ...] = ()
    """What stops holding if the assumption is wrong."""

    @model_validator(mode="after")
    def _verified_before_expiry(self) -> Assumption:
        if self.verified_on and self.expires_on and self.expires_on < self.verified_on:
            raise ValueError("expires_on is before verified_on")
        return self


class ResolutionMethod(StrEnum):
    """The way out. A question without one is a wish."""

    ASK = "ask"
    SPIKE = "spike"
    PROTOTYPE = "prototype"
    MEASURE = "measure"


class Question(Element):
    """An `unknown` with an owner and a way out.

    The answer is not a string here. It is the `Decision` that closed it, so
    the reasoning survives and the trace holds.
    """

    question: str = Field(min_length=1)
    method: ResolutionMethod = ResolutionMethod.ASK
    blocks: tuple[Ref, ...] = ()
    """What waits on the answer. Urgency is read from here, not from a date
    somebody guessed and nobody revisits."""
    resolved_by: Ref | None = None  # the decision that closed it


class Decision(Element):
    """A choice, with what it costs. The design's ADR."""

    context: str = ""
    choice: str = Field(min_length=1)
    consequences: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    applies_to: tuple[Ref, ...] = ()
    decided_on: date | None = None


class Rejection(Element):
    """Tried it, it was bad. It stops an agent proposing a dead idea again.

    The idea it rejects was never modelled, so `state: out_of_scope` has
    nothing to sit on. The rejection is the record, and the argument is in
    `body`.
    """

    applies_to: tuple[Ref, ...] = ()
    rejected_on: date | None = None
    milestone: Ref | None = None  # the slice that found out


# ------------------------------------------------------------------- slices


class Milestone(Element):
    """A vertical slice, and the envelope an agent works inside.

    A selection over the design plus a delta: `scope` says what may be
    touched, `must_hold` what may not break, `may_decide` where the agent is
    free, and `unresolved` which questions stay open on purpose. A milestone
    ends; the elements it selects do not.

    It never says how the work runs. No dates, no sizes, no assignees and no
    order: milestones are sequential, and the order is the order they are
    written in. Splitting a slice and tracking it belong to whatever consumes
    the packet, and a design that guessed at them would be wrong within a
    week and believed anyway.
    """

    outcome: str = ""
    includes: tuple[Ref, ...] = ()  # requirements, behaviors delivered
    scope: tuple[Ref, ...] = ()  # components, interfaces the agent may touch
    must_hold: tuple[Ref, ...] = ()  # decisions, quality requirements
    may_decide: tuple[str, ...] = ()
    """Explicit freedoms, in prose. Without them an agent either asks about
    everything or invents everything."""
    unresolved: tuple[Ref, ...] = ()  # questions knowingly left open
    done_when: tuple[ObservationId, ...] = ()


# -------------------------------------------------------------------- design


class Revision(Record):
    """One line of the change history."""

    version: str
    changed_on: date
    author: str
    summary: str = Field(min_length=1)


class Repository(Record):
    """A repository that holds part of the implementation.

    One design, many repositories. Every `implemented_by` entry reads
    `billing#src/refund.py`, and the prefix must be declared here, so a link
    into code resolves to a URL and a ref instead of to a guess.
    """

    id: Slug  # the prefix used in `implemented_by`
    url: str = Field(min_length=1)
    ref: str = "main"
    """A ref, never a pin."""


class Import(Record):
    """Another design this one points into.

    A `Ref` carries no location, so a foreign id looks like a local one. The
    checker indexes this design and its imports together; an id two designs
    both define is an error there, which keeps every id short.

    An import reaches the other design's `exports` and nothing else. Import
    cycles are an error: two designs that need each other are one design.
    """

    id: Ref  # "design:payments"
    source: str = Field(min_length=1)  # path or URL of the other design
    ref: str = "main"
    """A ref, never a pin."""
    expects: str = ""
    """The version range we assume of the other design, as for a library.
    Empty says nobody decided, so `check` cannot warn when the other side
    moves."""


class Note(Record):
    """A thought or a todo against the design, deliberately not an element.

    Not in `elements()`, never rendered, never packet input: an agent never
    sees a note. It asks for no title, state or owner, because the moment
    writing one needs a classification it stops being used. If it matters,
    it becomes a real element, and `promoted_to` records that.
    """

    id: Ref
    created_on: date
    text: str = ""
    about: tuple[Ref, ...] = ()
    """What it concerns. A ref, so renaming an element surfaces the note
    instead of leaving it stranded in prose. It may dangle: a note about
    something not yet written is the normal case, so `check` reports these
    and never fails on them."""
    done_on: date | None = None
    """A note somebody means to close is a todo. No second type for that."""
    promoted_to: Ref | None = None


class Design(Record):
    """Intent, requirements, architecture and gaps, for one system.

    A container plus its edges, and nothing computed. It is not a document:
    a specification, a diagram and a story sentence are all renderings of
    this, and an agent reads it whole.
    """

    format_version: int = FORMAT_VERSION
    id: Ref
    title: str = Field(min_length=1)
    version: str
    purpose: str = ""
    scope: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    """Written down, because a reader guesses wrong about what is missing."""
    exports: tuple[Ref, ...] = ()
    """The public surface: what another design may point at. Contract kinds
    only (`EXPORTABLE`), and only elements this design declares — to offer
    somebody else's interface, wrap it in one of ours, which makes it ours
    to keep. Everything unlisted is internal, and a foreign `Ref` into it is
    an error: without that rule two designs can never move apart, because
    any id is a dependency the moment somebody uses it. A long list is the
    smell, for the reason a long interface is."""
    revisions: tuple[Revision, ...] = ()
    imports: tuple[Import, ...] = ()
    repositories: tuple[Repository, ...] = ()

    glossary: tuple[Term, ...] = ()
    actors: tuple[Actor, ...] = ()
    goals: tuple[Goal, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    qualities: tuple[QualityRequirement, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    behaviors: tuple[Behavior, ...] = ()
    components: tuple[Component, ...] = ()
    interfaces: tuple[Interface, ...] = ()
    data_entities: tuple[DataEntity, ...] = ()
    resources: tuple[Resource, ...] = ()
    libraries: tuple[Library, ...] = ()
    external_services: tuple[ExternalService, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    decisions: tuple[Decision, ...] = ()
    questions: tuple[Question, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    milestones: tuple[Milestone, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    notes: tuple[Note, ...] = ()
    """Outside the graph on purpose. `elements()` does not yield them."""

    def elements(self) -> Iterator[Element]:
        """Every addressable element, in one pass. A checker starts here."""
        yield from self.glossary
        yield from self.actors
        yield from self.goals
        yield from self.requirements
        yield from self.qualities
        yield from self.constraints
        yield from self.behaviors
        yield from self.components
        yield from self.interfaces
        yield from self.data_entities
        yield from self.resources
        yield from self.libraries
        yield from self.external_services
        yield from self.assumptions
        yield from self.decisions
        yield from self.questions
        yield from self.rejections
        yield from self.milestones

    @model_validator(mode="after")
    def _exports_carry_contracts_only(self) -> Design:
        for ref in self.exports:
            if ref.split(":", 1)[0] not in EXPORTABLE:
                raise ValueError(f"{ref!r} is not a contract: export {sorted(EXPORTABLE)}")
        return self

    @model_validator(mode="after")
    def _ids_are_unique(self) -> Design:
        seen: set[str] = set()
        for element in self.elements():
            if element.id in seen:
                raise ValueError(f"duplicate id {element.id!r}")
            seen.add(element.id)
        return self
