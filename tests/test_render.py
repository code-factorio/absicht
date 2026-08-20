"""``absicht.render``: the read-only projections behind ``ab show``,
``ab gaps`` and ``ab trace``, and the site those pages become.

The command contracts — exit codes, flags, the bytes on stdout — live in
``tests/test_show_cli.py``, ``tests/test_gaps_cli.py``,
``tests/test_trace_cli.py`` and ``tests/test_render_cli.py``. What is pinned
here is the projections themselves, the shapes ``docs/tasks/26-render-site.md``
builds on ("literally reuse" the show view; "a gaps page, reusing 23-gaps.md's
worklist"), the note inbox page ``docs/tasks/60-addendum-render.md`` adds
(notes are store contents no ``Design`` carries, so they reach the site as an
argument), and the machinery the CLI tests cannot reach without a socket or
a clock:

- ``--depth`` bounds the *outgoing* side only; the inbound side is one hop at
  any depth, because expanding both directions is the pathfinding ``ab trace``
  owns and ``show`` deliberately does not (``docs/tasks/21-show.md`` left the
  choice open; this is the one it made, and the command's ``--help`` says so);
- expansion stops when the budget runs out, not when a walk revisits a node —
  a quality requirement scopes the very component that satisfies it right
  back, and the view of a cyclic graph is a bounded tree, not a search;
- a dangling ref resolves to no neighbour on either side, the same policy
  ``Index.referenced_by`` already holds: reporting dangling refs is ``ab
  check``'s job. ``broken/`` cannot reach this through the CLI (its two
  unreadable files are ``build``'s refusal), so the policy is pinned here on
  the folded design;
- the gaps worklist's boundaries no fixture holds, because a fixture pinned to
  "today" would rot: an external service expires strictly after its expiry
  date, a question a decision has already resolved leaves the worklist, and a
  question's urgency is read from what waits on the answer rather than from a
  date somebody guessed;
- the trace walk's cycle guard: a hop onto an element already on the current
  path is declined rather than followed, so a cyclic graph answers a bounded
  set of simple paths and says the guard fired instead of hanging;
- the site's byte determinism, with the clock injected rather than read, and
  the preview server's change detection and socket behaviour, decoupled from
  the poll loop's timing — the two things ``docs/tasks/26-render-site.md``
  names as too flaky to test through the loop itself.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

import pytest
from syrupy.assertion import SnapshotAssertion

from absicht.load import load_store
from absicht.models.design import (
    FORMAT_VERSION,
    Behavior,
    Component,
    ComponentLevel,
    DataEntity,
    Design,
    ExternalService,
    Interface,
    InterfaceStyle,
    Note,
    Observation,
    Outcome,
    QualityAttribute,
    QualityRequirement,
    Question,
    Relationship,
    RelationshipType,
    Requirement,
    Resource,
    ResourceKind,
    State,
    Timing,
)
from absicht.models.packet import Fidelity, Packet, PacketElement
from absicht.render import (
    SiteServer,
    UnknownRefError,
    generate_site,
    neighbourhood,
    packet_markdown,
    store_changed,
    store_snapshot,
    trace_paths,
    worklist,
)
from absicht.resolve import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "systems"


@pytest.fixture
def clean() -> Design:
    """The folded ``clean/`` design the assertions below walk."""
    return resolve(load_store(FIXTURES / "clean"))


def test_an_unknown_ref_raises_rather_than_answering_empty(clean: Design) -> None:
    """`ab show` maps this to `USAGE`: the caller asked for an element that is
    not there, which is a broken invocation, not a finding about the design."""

    with pytest.raises(UnknownRefError, match="component:ghost"):
        neighbourhood(clean, "component:ghost", depth=1)


def test_the_outgoing_side_expands_to_the_asked_depth_and_no_further(clean: Design) -> None:
    view = neighbourhood(clean, "component:cancellation", depth=2)

    assert [(hop.field, hop.other.id) for hop in view.outgoing] == [
        ("parent", "component:orders"),
        ("calls", "interface:order-events"),
        ("satisfies", "quality:cancel-latency"),
    ]
    orders = view.outgoing[0]
    assert [(hop.field, hop.other.id) for hop in orders.deeper] == [
        ("parent", "component:acme"),
        ("implements", "req:cancel-orders"),
        ("constrained_by", "constraint:gdpr-erasure"),
        ("depends_on", "library:pydantic"),
        ("depends_on", "resource:order-cache"),
        ("depends_on", "resource:order-stream"),
    ]
    quality = view.outgoing[2]
    assert [(hop.field, hop.other.id) for hop in quality.deeper] == [
        ("scope", "component:cancellation"),
    ]
    # Depth 2 stops at the fringe: `quality:cancel-latency` scopes this very
    # component right back — the cycle the budget must bound, not chase — and
    # every hop at the fringe is a leaf. Expanding those again is depth 3's job.
    assert all(hop.deeper == () for hop in (*orders.deeper, *quality.deeper))


def test_depth_zero_leaves_the_outgoing_side_unfollowed(clean: Design) -> None:
    """Zero hops means the element's own refs are not followed — the view is
    the element plus whoever points at it, and `--depth 0` must not quietly
    mean the same as the default."""

    view = neighbourhood(clean, "component:cancellation", depth=0)

    assert view.outgoing == ()
    assert view.incoming != ()


def test_depth_three_reaches_a_third_hop(clean: Design) -> None:
    """The budget decrements once per level, not once per two: the component
    that `quality:cancel-latency` scopes right back gets its own outgoing
    edges at the third hop. The cycle makes this the sharp end of the depth
    arithmetic — one level early or late and the fringe moves."""

    view = neighbourhood(clean, "component:cancellation", depth=3)

    scoped = view.outgoing[2].deeper[0]
    assert (scoped.field, scoped.other.id) == ("scope", "component:cancellation")
    assert [hop.other.id for hop in scoped.deeper] == [
        "component:orders",
        "interface:order-events",
        "quality:cancel-latency",
    ]


def test_the_inbound_side_stays_one_hop_at_any_depth(clean: Design) -> None:
    """A depth that deep would find more if the inbound side expanded too —
    `component:orders` is pointed at by seven elements whose own refs go
    further out, and none of those refs joins the view."""

    view = neighbourhood(clean, "component:orders", depth=5)

    assert [(link.field, link.other.id) for link in view.incoming] == [
        ("at", "behavior:order-cancelled"),
        ("at", "behavior:order-placed"),
        ("parent", "component:cancellation"),
        ("declared_by", "interface:order-events"),
        ("owner_component", "data:order"),
        ("applies_to", "decision:event-log"),
        ("scope", "milestone:m1"),
    ]


def test_a_dangling_ref_resolves_to_no_neighbour() -> None:
    design = resolve(load_store(FIXTURES / "broken"))

    view = neighbourhood(design, "component:dangling", depth=2)

    # `dangling`'s two refs are `parent: component:root`, which resolves, and
    # an `implements` edge onto `req:ghost`, which no file defines: the ghost
    # must not appear as a neighbour, and the view is still a successful one —
    # `ab show` reports neighbourhoods, `ab check` reports the ghost.
    assert [(hop.field, hop.other.id) for hop in view.outgoing] == [
        ("parent", "component:root"),
    ]


def test_json_carries_the_full_view_and_the_body_flag(clean: Design) -> None:
    view = neighbourhood(clean, "behavior:order-placed", depth=2)

    with_body = view.render_json(include_body=True)
    without_body = view.render_json(include_body=False)

    assert with_body["format_version"] == FORMAT_VERSION
    assert with_body["element"]["body"].startswith("Kept because it is the record")
    assert "body" not in without_body["element"]
    hop = with_body["points_at"][0]
    assert hop["field"] == "at"
    assert hop["target"]["id"] == "component:orders"
    # Neighbours carry their fields but never prose or provenance: the body is
    # the focus element's, and where a neighbour lives is `source`'s story.
    assert "body" not in hop["target"]
    assert "source" not in hop["target"]
    assert [(deeper["field"], deeper["target"]["id"]) for deeper in hop["deeper"]] == [
        ("parent", "component:acme"),
        ("implements", "req:cancel-orders"),
        ("constrained_by", "constraint:gdpr-erasure"),
        ("depends_on", "library:pydantic"),
        ("depends_on", "resource:order-cache"),
        ("depends_on", "resource:order-stream"),
    ]
    assert hop["deeper"][0]["deeper"] == []
    assert [(link["field"], link["source"]["id"]) for link in with_body["referenced_by"]] == [
        ("supersedes", "behavior:order-placed-v2"),
        ("at", "behavior:order-placed-v2"),
    ]


# --- the gaps worklist --------------------------------------------------------

# The three worklist boundaries no fixture can hold: each would need "today"
# baked into the store, and rot the day after. Hand-built designs instead,
# with the clock injected the way `ab check`'s policy layer already runs.
TODAY = date(2026, 8, 16)


def test_worklist_marks_delegated_elements_unfinished() -> None:
    """`delegated` is the third unfinished state and the one no fixture holds:
    decided-elsewhere is still unfinished, and without an owner the element is
    on the list twice over."""
    design = Design(
        id="design:tiny",
        title="Tiny",
        version="0.1.0",
        components=(
            Component(
                id="component:outsourced",
                title="Outsourced",
                level=ComponentLevel.CONTAINER,
                state=State.DELEGATED,
            ),
        ),
    )

    (only,) = worklist(design, today=TODAY)

    assert only.element.id == "component:outsourced"
    assert only.reasons == ("state=delegated", "unowned")


def test_worklist_reads_a_questions_urgency_from_what_waits_on_the_answer() -> None:
    """The whole kind is a gap by construction, and what separates one entry
    from the next is what blocks on it — urgency read from the graph, never
    from a date somebody guessed and nobody revisits. A question a decision
    has already resolved is nobody's worklist entry, whatever its state
    says."""
    design = Design(
        id="design:tiny",
        title="Tiny",
        version="0.1.0",
        components=(
            Component(
                id="component:waiting",
                title="Waiting",
                level=ComponentLevel.CONTAINER,
                state=State.SPECIFIED,
                owner="a",
            ),
        ),
        questions=(
            Question(id="question:open", title="Open", owner="a", question="How long?"),
            Question(
                id="question:blocking",
                title="Blocking",
                owner="a",
                question="Which way round?",
                blocks=("component:waiting",),
            ),
            Question(
                id="question:closed",
                title="Closed",
                owner="a",
                state=State.SPECIFIED,
                question="Settled already.",
                blocks=("component:waiting",),
                resolved_by="decision:done",
            ),
        ),
    )

    by_id = {gap.element.id: gap for gap in worklist(design, today=TODAY)}

    assert by_id["question:open"].reasons == ("state=unknown", "question-open")
    assert by_id["question:blocking"].reasons == ("state=unknown", "question-blocking")
    # What waits on the answer travels with the entry, so a consumer can
    # prioritize without re-reading the element.
    assert by_id["question:open"].blocks == ()
    assert by_id["question:blocking"].blocks == ("component:waiting",)
    assert "question:closed" not in by_id


def test_worklist_expires_an_external_service_strictly_after_its_expiry_date() -> None:
    """`expires_on` means "after this, re-check": the day itself is still
    trusted — `absicht.check`'s reading, and necessarily this one's too,
    because the worklist reuses that module's one spelling of "expired"
    rather than re-deriving the comparison."""
    design = Design(
        id="design:tiny",
        title="Tiny",
        version="0.1.0",
        external_services=(
            ExternalService(
                id="external:today",
                title="Today",
                state=State.SPECIFIED,
                owner="ops",
                expires_on=TODAY,
            ),
            ExternalService(
                id="external:yesterday",
                title="Yesterday",
                state=State.SPECIFIED,
                owner="ops",
                expires_on=TODAY - timedelta(days=1),
            ),
        ),
    )

    (only,) = worklist(design, today=TODAY)

    assert only.element.id == "external:yesterday"
    assert only.reasons == ("external-expired",)
    assert only.expires_on == TODAY - timedelta(days=1)


def test_worklist_gaps_a_behavior_with_no_observations() -> None:
    """The query-side twin of `policy/behavior-unobserved`: the expectation
    with nothing observable is unfinished whatever its state — a `specified`
    behavior lands on the worklist for that reason alone."""
    design = Design(
        id="design:tiny",
        title="Tiny",
        version="0.1.0",
        behaviors=(
            Behavior(
                id="behavior:bare",
                title="Bare",
                state=State.SPECIFIED,
                owner="a",
                trigger="Something happens.",
            ),
        ),
    )

    (only,) = worklist(design, today=TODAY)

    assert only.element.id == "behavior:bare"
    assert only.reasons == ("no-observations",)


def test_worklist_inherits_the_single_referencing_owner() -> None:
    """§7 in the worklist: an unowned `unknown` with exactly one referencing
    owner answers to it — carried on the entry, never stored — and stops
    being `unowned`; an own owner, a second referencing owner, or an
    ownerless referencer means it does not. `req:deep`'s only referencer is
    the ownerless `component:mid`, whose own inherited owner (platform, via
    `quality:top`) is never chained on: one level, no deeper."""
    design = Design(
        id="design:tiny",
        title="Tiny",
        version="0.1.0",
        components=(
            Component(
                id="component:carrier",
                title="Carrier",
                level=ComponentLevel.CONTAINER,
                state=State.SPECIFIED,
                owner="platform",
            ),
            Component(
                id="component:rival",
                title="Rival",
                level=ComponentLevel.CONTAINER,
                state=State.SPECIFIED,
                owner="rival-team",
            ),
            Component(id="component:mid", title="Mid", level=ComponentLevel.CONTAINER),
        ),
        requirements=(
            Requirement(id="req:watched", title="Watched", statement="Something must happen."),
            Requirement(
                id="req:owned", title="Owned", statement="Something must happen.", owner="qa"
            ),
            Requirement(id="req:contested", title="Contested", statement="Something must happen."),
            Requirement(id="req:deep", title="Deep", statement="Something must happen."),
        ),
        qualities=(
            QualityRequirement(
                id="quality:top",
                title="Top",
                state=State.SPECIFIED,
                owner="platform",
                attribute=QualityAttribute.LATENCY,
                scope=("component:mid",),
            ),
        ),
        relationships=(
            Relationship(
                source_id="component:carrier",
                target_id="req:watched",
                type=RelationshipType.IMPLEMENTS,
            ),
            Relationship(
                source_id="component:carrier",
                target_id="req:owned",
                type=RelationshipType.IMPLEMENTS,
            ),
            Relationship(
                source_id="component:carrier",
                target_id="req:contested",
                type=RelationshipType.IMPLEMENTS,
            ),
            Relationship(
                source_id="component:rival",
                target_id="req:contested",
                type=RelationshipType.IMPLEMENTS,
            ),
            Relationship(
                source_id="component:mid",
                target_id="req:deep",
                type=RelationshipType.IMPLEMENTS,
            ),
        ),
    )

    by_id = {gap.element.id: gap for gap in worklist(design, today=TODAY)}

    assert by_id["req:watched"].owner_inherited == "platform"
    assert by_id["req:watched"].reasons == ("state=unknown",)
    assert by_id["req:owned"].owner_inherited is None
    assert by_id["req:owned"].reasons == ("state=unknown",)
    assert by_id["req:contested"].owner_inherited is None
    assert by_id["req:contested"].reasons == ("state=unknown", "unowned")
    assert by_id["component:mid"].owner_inherited == "platform"
    assert by_id["req:deep"].owner_inherited is None
    assert by_id["req:deep"].reasons == ("state=unknown", "unowned")


# --- observations in the show view ----------------------------------------------


def test_the_effective_timing_follows_the_resource_kind_when_unsaid() -> None:
    """§1.2's table, as the show view spells it: an authored timing wins, an
    unsaid one follows what `at` resolved to — a stream defaults eventual,
    everything else immediate — and `must_not` has no timing to render, at
    no point having no when."""
    design = Design(
        id="design:tiny",
        title="Tiny",
        version="0.1.0",
        components=(
            Component(
                id="component:c",
                title="C",
                level=ComponentLevel.CONTAINER,
                state=State.SPECIFIED,
                owner="a",
            ),
        ),
        resources=(
            Resource(
                id="resource:events",
                title="Events",
                state=State.SPECIFIED,
                owner="a",
                resource_kind=ResourceKind.STREAM,
                technology="Kafka",
            ),
        ),
        behaviors=(
            Behavior(
                id="behavior:emits",
                title="Emits",
                state=State.SPECIFIED,
                owner="a",
                trigger="A message is published.",
                observations=(
                    Observation(
                        id="behavior:emits#obs-1",
                        statement="An event is emitted",
                        at="resource:events",
                        outcome=Outcome.MUST,
                    ),
                    Observation(
                        id="behavior:emits#obs-2",
                        statement="A component acted",
                        at="component:c",
                        outcome=Outcome.MUST,
                    ),
                    Observation(
                        id="behavior:emits#obs-3",
                        statement="Nothing is logged",
                        at="resource:events",
                        outcome=Outcome.MUST_NOT,
                    ),
                    Observation(
                        id="behavior:emits#obs-4",
                        statement="An event lands now",
                        at="resource:events",
                        outcome=Outcome.MUST,
                        timing=Timing.IMMEDIATE,
                    ),
                ),
            ),
        ),
    )

    view = neighbourhood(design, "behavior:emits", depth=1)

    assert [observation.effective_timing for observation in view.observations] == [
        Timing.EVENTUAL,  # unsaid, at a stream
        Timing.IMMEDIATE,  # unsaid, at a non-resource
        None,  # must_not: at no point, no when
        Timing.IMMEDIATE,  # authored, and the authored value wins
    ]


# --- the trace paths -----------------------------------------------------------


def test_a_cycle_ends_the_walk_and_says_so() -> None:
    """`broken/`'s `parent` cycle is the input the walk must survive: the
    guard is the simple-path invariant — a hop onto an element already on the
    current path is declined — so the answer is a bounded set of paths plus
    `cycle_hit`, not a hang. Exactly the two one-hop paths exist (down
    through the edge loop-a authors, up through the one loop-b authors); the
    hop back is declined both ways. `broken/` cannot reach this through the
    CLI (its two unreadable files are `build`'s refusal), so the guard is
    pinned here on the folded design."""
    design = resolve(load_store(FIXTURES / "broken"))

    result = trace_paths(design, "component:loop-a")

    assert [tuple((step.field, step.up, step.ref) for step in path) for path in result.paths] == [
        (("parent", False, "component:loop-b"),),
        (("parent", True, "component:loop-b"),),
    ]
    assert result.cycle_hit is True


def test_an_unknown_to_ref_raises_rather_than_answering_empty(clean: Design) -> None:
    """`ab trace` maps this to `USAGE`: "no path to a nonexistent element" is
    not an answer anyone should be able to mistake for a route check."""
    with pytest.raises(UnknownRefError, match="decision:never"):
        trace_paths(clean, "req:cancel-orders", to="decision:never-made")


def _dense() -> Design:
    """A three-layer fan — one requirement, four components, four interfaces,
    four data entities, every layer fully cross-linked — the smallest shape
    whose simple-path count says what a realistically dense store says: the
    complete enumeration `trace_paths` promises is exponential, and a real
    store (absicht's own, 121 elements) reaches millions of paths for a single
    start.

    Built rather than loaded because no fixture should carry a shape whose
    purpose is to be too big to walk.
    """
    width = 4
    components = tuple(
        Component(id=f"component:c{i}", title=f"C{i}", level=ComponentLevel.CONTAINER)
        for i in range(width)
    )
    interfaces = tuple(
        Interface(id=f"interface:s{j}", title=f"S{j}", style=InterfaceStyle.EVENT)
        for j in range(width)
    )
    data = tuple(DataEntity(id=f"data:d{k}", title=f"D{k}") for k in range(width))
    return Design(
        id="design:dense",
        title="Dense",
        version="0.1.0",
        requirements=(Requirement(id="req:r", title="R", statement="Something must happen."),),
        components=components,
        interfaces=interfaces,
        data_entities=data,
        # Every edge lives in `relationships` now, which is what lets each
        # layer be complete against the next: a single-owner field could only
        # ever spell one of the sixteen.
        relationships=(
            *(
                Relationship(
                    source_id=component.id, target_id="req:r", type=RelationshipType.IMPLEMENTS
                )
                for component in components
            ),
            *(
                Relationship(
                    source_id=component.id,
                    target_id=interface.id,
                    type=RelationshipType.IMPLEMENTS,
                )
                for component in components
                for interface in interfaces
            ),
            *(
                Relationship(
                    source_id=interface.id, target_id=entity.id, type=RelationshipType.RELATES_TO
                )
                for interface in interfaces
                for entity in data
            ),
        ),
    )


def test_the_walk_stops_at_the_path_limit_and_says_so() -> None:
    """The limit is a budget on materialized paths, spent in deterministic
    walk order: exactly `limit` paths come back, the flag says the answer was
    cut short rather than complete, and the paths that did come back are the
    first `limit` of the uncapped enumeration — the same walk, stopped
    earlier, never a different order."""
    full = trace_paths(_dense(), "req:r", limit=None)
    # Both directions by default, so the reverse edges multiply too: this
    # three-layer fan of four holds 127,476 simple paths from one start —
    # the explosion in miniature, and the count the fixture is built to pin.
    assert len(full.paths) == 127_476
    assert full.truncated is False

    capped = trace_paths(_dense(), "req:r", limit=10)

    assert len(capped.paths) == 10
    assert capped.paths == full.paths[:10]
    assert capped.truncated is True


def test_the_limit_reached_note_renders_in_every_format() -> None:
    """A truncated trace must not read as exhaustive in any of the three
    formats — the same discipline `cycle_hit` already follows, one spelling
    per format, additive in `--json`."""
    capped = trace_paths(_dense(), "req:r", limit=1)

    assert "path limit" in capped.render_text()
    assert capped.render_json()["truncated"] is True


# --- the packet document -------------------------------------------------------------


def _packet_document() -> str:
    """One packet exercising everything `clean/`'s milestone leaves empty: two
    scope blocks (one with prose), a ring element, every obligation list
    carrying content, and a done-when list pointing at the rendered features.

    Built by hand rather than assembled, because what is under test is the
    rendering of the model, not the selection that fills it — and a packet that
    silently dropped its `must_hold` ADRs or an element's prose passes every
    fixture-driven test the CLI modules run."""
    return packet_markdown(
        Packet(
            milestone="milestone:m",
            design="design:tiny",
            outcome="The thing works.",
            elements=(
                PacketElement(
                    ref="milestone:m",
                    fidelity=Fidelity.FULL,
                    element={"id": "milestone:m", "title": "M", "body": ""},
                ),
                PacketElement(
                    ref="component:core",
                    fidelity=Fidelity.FULL,
                    element={
                        "id": "component:core",
                        "title": "Core",
                        "state": "",
                        "responsibility": "Do things",
                        "tags": [],
                        "owner": None,
                        "body": "Prose that must survive.\n\n",
                    },
                ),
                PacketElement(
                    ref="component:side",
                    fidelity=Fidelity.FULL,
                    element={"id": "component:side", "title": "Side", "body": ""},
                ),
                PacketElement(
                    ref="interface:edge",
                    fidelity=Fidelity.CONTRACT,
                    element={"id": "interface:edge", "title": "Edge"},
                ),
            ),
            must_hold=("decision:adr", "quality:latency"),
            may_decide=("the retry policy",),
            unresolved=("question:q",),
            rejections=("rejection:big-bang",),
            done_when=("behavior:cancel#obs-1", "behavior:cancel#obs-2"),
        ),
        features_dir="features",
    )


def test_packet_markdown_carries_every_obligation_and_each_scope_block() -> None:
    document = _packet_document()

    assert document.startswith("# Packet: M\n\n`milestone:m` — The thing works.\n")
    # Two scope blocks, both present — the second must not clobber the first —
    # separated by a blank line, prose included and trailing blank lines gone,
    # with the prose itself a blank line after the last field.
    assert "### Core" in document
    assert "- responsibility: Do things\n\nProse that must survive.\n\n### Side" in document
    # Empty-valued fields and the header four stay out of the bullet list.
    for absent in ("- tags:", "- owner:", "- body:", "- id:", "- title:", "- state:"):
        assert absent not in document
    # The ring stays summarized to one line, never a block of its own.
    assert "- `interface:edge` — Edge" in document
    assert "### Edge" not in document
    # Every obligation section lists what it carries, not `(none)` — checked
    # per section, because the behavior sections legitimately spell an empty
    # list out (nothing to satisfy is a fact an agent acts on).
    for heading, carried in (
        ("## Must hold", "- `decision:adr`"),
        ("## May decide", "- the retry policy"),
        ("## Unresolved", "- `question:q`"),
        ("## Rejections", "- `rejection:big-bang`"),
    ):
        section = document.split(heading, 1)[1].split("\n## ", 1)[0]
        assert carried in section
        assert "(none)" not in section
    # Done-when is the observation ids themselves, and the pointer to where
    # the full Gherkin landed as the caller spelled it.
    done_when = document.split("## Done when", 1)[1]
    assert "- `behavior:cancel#obs-1`\n- `behavior:cancel#obs-2`" in done_when
    assert "Full Gherkin: the `.feature` files under `features/`." in done_when


def test_packet_markdown_drops_the_dash_when_the_outcome_is_empty() -> None:
    """No outcome, no hanging `—`: the identity line is the bare ref, and a
    scope-less milestone still spells the section rather than vanishing."""
    document = packet_markdown(
        Packet(
            milestone="milestone:m",
            design="design:tiny",
            elements=(
                PacketElement(
                    ref="milestone:m",
                    fidelity=Fidelity.FULL,
                    element={"id": "milestone:m", "title": "M"},
                ),
            ),
        )
    )

    assert "`milestone:m`\n\n## Scope\n\n(none)" in document


def _behavior_packet() -> Packet:
    """One packet carrying both behavior lists with everything
    docs/tasks/57-packet-behaviors.md demands of the document: a satisfy
    behavior composing another behavior one hop out, which references a third
    without expanding it, a second satisfy behavior (two blocks, so a renderer
    cannot clobber one with the other), a must-not-break observation with no
    timing to spell, and a listed ref the packet carries nowhere. Built by
    hand like `_packet_document`, for the same reason: what is under test is
    the rendering of the model, not the selection that fills it."""

    def observation(
        observation_id: str, statement: str, at: str, outcome: str, effective: str | None
    ) -> dict[str, object]:
        """One observation exactly as assembly carries it: the authored dump
        with the derived ``effective_timing`` beside it."""
        return {
            "id": observation_id,
            "statement": statement,
            "at": at,
            "outcome": outcome,
            "timing": None,
            "effective_timing": effective,
        }

    def behavior(ref: str, title: str, observations: list[dict[str, object]]) -> PacketElement:
        return PacketElement(
            ref=ref,
            fidelity=Fidelity.FULL,
            element={
                "id": ref,
                "title": title,
                "trigger": f"{title} happens.",
                "lifecycle": "active",
                "observations": observations,
                "body": "",
            },
        )

    return Packet(
        milestone="milestone:m",
        design="design:tiny",
        outcome="The thing keeps working.",
        elements=(
            PacketElement(
                ref="milestone:m",
                fidelity=Fidelity.FULL,
                element={"id": "milestone:m", "title": "M"},
            ),
            PacketElement(
                ref="component:core",
                fidelity=Fidelity.FULL,
                element={"id": "component:core", "title": "Core", "body": ""},
            ),
            behavior(
                "behavior:a",
                "A happens",
                [
                    observation(
                        "behavior:a#obs-1",
                        "A observes the core",
                        "component:core",
                        "must",
                        "immediate",
                    ),
                    observation(
                        "behavior:a#obs-2", "A makes B occur", "behavior:b", "must", "eventual"
                    ),
                ],
            ),
            behavior(
                "behavior:b",
                "B happens",
                [
                    observation(
                        "behavior:b#obs-1", "B makes C occur", "behavior:c", "must", "eventual"
                    )
                ],
            ),
            behavior(
                "behavior:flat",
                "Flat holds",
                [
                    observation(
                        "behavior:flat#obs-1",
                        "Flat observes the core",
                        "component:core",
                        "must",
                        "immediate",
                    )
                ],
            ),
            behavior(
                "behavior:guard",
                "The guard holds",
                [
                    observation(
                        "behavior:guard#obs-1", "Nothing leaks", "resource:log", "must_not", None
                    )
                ],
            ),
        ),
        satisfy=("behavior:ghost", "behavior:a", "behavior:flat"),
        must_not_break=("behavior:guard",),
    )


def test_packet_markdown_separates_the_two_behavior_lists() -> None:
    document = packet_markdown(_behavior_packet())

    satisfy_at = document.index("## Behaviors to satisfy")
    not_break_at = document.index("## Behaviors that must not break")
    # Two clearly separated sections, the work before the guardrails.
    assert satisfy_at < not_break_at
    satisfy_section = document[satisfy_at:not_break_at]
    # A listed ref the packet carries nowhere still says it was named, and the
    # walk continues past it: every block after it renders too.
    assert "- `behavior:ghost`" in satisfy_section
    assert "### A happens" in satisfy_section
    assert "### Flat holds" in satisfy_section
    # Blocks are separated by one blank line, and the second cannot clobber
    # the first: A's nested hop ends, a blank line, then Flat's own block.
    assert "(must, eventual, at behavior:c)\n\n### Flat holds" in satisfy_section
    # The satisfy block with its observations, the effective timing spelled so
    # the agent never computes a default.
    assert "`behavior:a`" in satisfy_section
    assert (
        "- `behavior:a#obs-1` — A observes the core (must, immediate, at component:core)"
        in satisfy_section
    )
    assert (
        "- `behavior:a#obs-2` — A makes B occur (must, eventual, at behavior:b)" in satisfy_section
    )
    # The must-not-break section leads with the addendum's framing: standing
    # expectations, and breaking one is a regression.
    not_break_section = document[not_break_at:]
    assert "Standing expectations" in not_break_section
    assert "regression" in not_break_section
    # A `must_not` observation has no when to spell.
    assert "### The guard holds" in not_break_section
    assert (
        "- `behavior:guard#obs-1` — Nothing leaks (must_not, at resource:log)" in not_break_section
    )
    # Behaviors the sections own do not duplicate into Scope.
    scope = document.split("## Scope", 1)[1].split("\n## ", 1)[0]
    assert "behavior:" not in scope


def test_packet_markdown_expands_composition_one_hop_and_no_further() -> None:
    document = packet_markdown(_behavior_packet())

    # B joins under the behavior that composes it, observations included, one
    # blank line after the observation that pulled it in.
    assert "(must, eventual, at behavior:b)\n\n#### Composes: `behavior:b` — B happens" in document
    assert "- `behavior:b#obs-1` — B makes C occur (must, eventual, at behavior:c)" in document
    # C stays what that observation references — expanded nowhere — and only a
    # behavior ref ever nests: an observation at a carried component is not a
    # composition edge.
    assert "Composes: `behavior:c`" not in document
    assert "Composes: `component:core`" not in document


# --- the site --------------------------------------------------------------------


def test_an_unknown_scope_ref_raises_rather_than_rendering_everything(
    clean: Design, tmp_path: Path
) -> None:
    """An ignored `--scope` would quietly render the whole store — the same
    empty-answer trap `show` and `trace` refuse, so the site refuses it too."""
    with pytest.raises(UnknownRefError, match="component:ghost"):
        generate_site(clean, tmp_path, today=TODAY, scope="component:ghost")


def _site_bytes(out: Path) -> dict[str, bytes]:
    """The site as ``path → bytes``: the shape a determinism claim compares."""
    return {
        path.relative_to(out).as_posix(): path.read_bytes() for path in sorted(out.rglob("*.html"))
    }


def test_the_site_is_byte_identical_across_runs(clean: Design, tmp_path: Path) -> None:
    """`today` is injected rather than read, so nothing between the store and
    the bytes reads a clock: the same design spells the same site twice — the
    property `docs/maintainers/verification.md`'s determinism job cross-checks
    from a clean checkout."""

    generate_site(clean, tmp_path / "first", today=TODAY)
    generate_site(clean, tmp_path / "second", today=TODAY)

    first = _site_bytes(tmp_path / "first")
    assert first == _site_bytes(tmp_path / "second")
    assert len(first) == 26  # twenty-two element pages, index, traceability, gaps, inbox


# --- the note inbox page ----------------------------------------------------------


def _note(
    note_id: str,
    created: date,
    *,
    text: str = "A thought.",
    about: str | None = None,
    promoted_to: str | None = None,
) -> Note:
    """One note as the loader would deliver it, with the clock already folded
    into `created` — the page's ages hang on the injected `today`, never on a
    wall clock."""
    return Note(
        id=note_id,
        created_on=created,
        about=(about,) if about else (),
        promoted_to=promoted_to,
        text=text,
    )


def test_the_inbox_page_headlines_the_age_and_runs_oldest_first(
    clean: Design, tmp_path: Path
) -> None:
    """§6's pressure reading, on the page: the headline names the count and
    the age of the oldest against the injected `today` — a bare count is not
    useful pressure — and the list runs oldest first, the same order `ab note
    list` prints (the headline and the ages are that command's spellings,
    shared, not a second humanizer)."""
    notes = (
        _note("note:newer1", TODAY, text="Fresh."),
        _note("note:older1", TODAY - timedelta(days=90), text="Old."),
    )

    generate_site(clean, tmp_path, today=TODAY, notes=notes)

    page = (tmp_path / "notes.html").read_text(encoding="utf-8")
    assert "<h1>Note inbox</h1>" in page
    assert "<p>2 notes, oldest 3 months</p>" in page
    assert page.index("note:older1") < page.index("note:newer1")


def test_the_inbox_page_renders_bodies_anchors_and_the_promotion_archive(
    clean: Design, tmp_path: Path
) -> None:
    """The inbox at reading width: each text rendered as prose, the anchor
    linked when the site holds its page and plain text when nothing defines it
    (a dangling `about` is `ab check`'s finding, not a dead link), and promoted
    notes archived under what they became — the record of what became what is
    part of the design story, so promotion leaves the inbox, never the store."""
    notes = (
        _note(
            "note:free01",
            TODAY - timedelta(days=45),
            text="Look at cancellation.\n\nTwice.",
            about="component:cancellation",
        ),
        _note(
            "note:lost01",
            TODAY - timedelta(days=3),
            text="Points nowhere yet.",
            about="component:ghost",
        ),
        _note(
            "note:gone01",
            TODAY - timedelta(days=60),
            text="Became a requirement.",
            promoted_to="req:cancel-orders",
        ),
    )

    generate_site(clean, tmp_path, today=TODAY, notes=notes)

    page = (tmp_path / "notes.html").read_text(encoding="utf-8")
    # The headline counts the inbox only: promotion removed `note:gone01` from
    # it — and the oldest unpromoted is 45 days old, six weeks in the rough
    # buckets (weeks up to 60 days, months from there).
    assert "<p>2 notes, oldest 6 weeks</p>" in page
    assert "<p>Look at cancellation.</p>" in page
    assert "<p>Twice.</p>" in page
    assert '<a href="elements/component/cancellation.html">component:cancellation</a>' in page
    assert "<code>component:ghost</code>" in page
    archived = page.index("<h2>Promoted</h2>")
    assert archived < page.index("note:gone01")
    assert 'became <a href="elements/req/cancel-orders.html">' in page


def test_an_empty_inbox_still_has_its_page(clean: Design, tmp_path: Path) -> None:
    """A store with no notes still writes the page — a missing page would read
    as "render forgot the inbox" — and says there are none, like the gaps
    page's empty stretch."""
    generate_site(clean, tmp_path, today=TODAY)

    assert "<p>0 notes</p>" in (tmp_path / "notes.html").read_text(encoding="utf-8")


def test_notes_never_become_element_pages(clean: Design, tmp_path: Path) -> None:
    """The inbox is a list, not nodes (§6): a note joins no index group, no
    traceability view, and gets no element page even when the store holds it —
    the page count the site test pins stays what it was."""
    generate_site(clean, tmp_path, today=TODAY, notes=(_note("note:a11111", TODAY),))

    assert not (tmp_path / "elements" / "note").exists()
    for page in ("index.html", "trace.html", "gaps.html"):
        assert "note:a11111" not in (tmp_path / page).read_text(encoding="utf-8")


def test_the_inbox_page_is_snapshotted(
    clean: Design, tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """The golden inbox of docs/tasks/60-addendum-render.md: one anchored
    note, one plain, one promoted — ages against the injected `today`, so the
    bytes never rot with the calendar."""
    notes = (
        _note(
            "note:anchr1",
            TODAY - timedelta(days=45),
            text="The order cache needs a TTL.\n\nMeasure before deciding.",
            about="resource:order-cache",
        ),
        _note("note:plain01", TODAY - timedelta(days=3), text="Ask finance about refunds."),
        _note(
            "note:gone01",
            TODAY - timedelta(days=60),
            text="Became a requirement.",
            promoted_to="req:cancel-orders",
        ),
    )

    generate_site(clean, tmp_path, today=TODAY, notes=notes)

    assert (tmp_path / "notes.html").read_text(encoding="utf-8") == snapshot


def test_the_change_detection_notices_edits_additions_and_removals(tmp_path: Path) -> None:
    """The poll loop's whole judgement in one pair of functions, decoupled from
    the loop: docs/tasks/26-render-site.md asks for exactly this unit test
    instead of a timing-dependent one on the server itself."""

    store = tmp_path / "store"
    (store / "requirements").mkdir(parents=True)
    element = store / "requirements" / "r.md"
    element.write_text("---\nid: req:r\n---\n", encoding="utf-8")

    before = store_snapshot(store)
    assert not store_changed(store, before)

    # A touch far from any plausible real mtime, so the verdict is the
    # detection's, not the filesystem's.
    os.utime(element, ns=(2**40, 2**40))
    assert store_changed(store, before)

    (store / "design.yaml").write_text("id: design:s\n", encoding="utf-8")
    assert store_changed(store, before)

    after = store_snapshot(store)
    element.unlink()
    assert store_changed(store, after)


def test_the_preview_server_serves_the_site_and_stops_cleanly(
    clean: Design, tmp_path: Path
) -> None:
    """The spec's `--serve` minimum: starts, serves the index page (and a
    nested element page, proving the directory mapping), shuts down cleanly.
    Port 0 asks for an ephemeral one so the test never collides."""
    out = tmp_path / "site"
    generate_site(clean, out, today=TODAY)
    server = SiteServer(out, 0)

    server.start()
    try:
        assert server.port > 0
        with urlopen(f"http://127.0.0.1:{server.port}/index.html") as response:
            assert response.status == 200
            assert response.read() == (out / "index.html").read_bytes()
        with urlopen(f"http://127.0.0.1:{server.port}/elements/component/orders.html") as nested:
            assert nested.status == 200
    finally:
        server.stop()
