"""``absicht.render``: the read-only projections behind ``ab show``,
``ab gaps`` and ``ab trace``, and the site those pages become.

The command contracts — exit codes, flags, the bytes on stdout — live in
``tests/test_show_cli.py``, ``tests/test_gaps_cli.py``,
``tests/test_trace_cli.py`` and ``tests/test_render_cli.py``. What is pinned
here is the projections themselves, the shapes ``docs/tasks/26-render-site.md``
builds on ("literally reuse" the show view; "a gaps page, reusing 23-gaps.md's
worklist") and the machinery the CLI tests cannot reach without a socket or
a clock:

- ``--depth`` bounds the *outgoing* side only; the inbound side is one hop at
  any depth, because expanding both directions is the pathfinding ``ab trace``
  owns and ``show`` deliberately does not (``docs/tasks/21-show.md`` left the
  choice open; this is the one it made, and the command's ``--help`` says so);
- expansion stops when the budget runs out, not when a walk revisits a node —
  a seam's provider provides that seam right back, and the view of a cyclic
  graph is a bounded tree, not a search;
- a dangling ref resolves to no neighbour on either side, the same policy
  ``Index.referenced_by`` already holds: reporting dangling refs is ``ab
  check``'s job. ``broken/`` cannot reach this through the CLI (its two
  unreadable files are ``build``'s refusal), so the policy is pinned here on
  the folded design;
- the gaps worklist's date boundaries — the ones no fixture holds, because a
  fixture pinned to "today" would rot: a question turns overdue strictly after
  its due date, an external expires strictly after its expiry date, and a
  question a decision has already resolved leaves the worklist;
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

from absicht.load import load_store
from absicht.models import (
    SCHEMA_VERSION,
    Behavior,
    Component,
    Criterion,
    CriterionKind,
    Design,
    External,
    ExternalKind,
    Fidelity,
    Observation,
    Outcome,
    Packet,
    PacketElement,
    Question,
    Requirement,
    Resource,
    ResourceKind,
    State,
    Story,
    System,
    Timing,
)
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
    view = neighbourhood(clean, "seam:order-events", depth=2)

    assert [(hop.field, hop.other.id) for hop in view.outgoing] == [
        ("provider", "component:orders"),
        ("consumers", "component:cancellation"),
        ("carries", "data:order"),
    ]
    orders = view.outgoing[0]
    assert [(hop.field, hop.other.id) for hop in orders.deeper] == [
        ("contains", "component:catalog"),
        ("provides", "seam:order-events"),
        ("owns_data", "data:order"),
    ]
    # Depth 2 stops at the fringe: `orders` provides this very seam right
    # back — the cycle the budget must bound, not chase — and every hop at the
    # fringe is a leaf. Expanding those again is depth 3's job.
    assert all(hop.deeper == () for hop in orders.deeper)


def test_depth_zero_leaves_the_outgoing_side_unfollowed(clean: Design) -> None:
    """Zero hops means the element's own refs are not followed — the view is
    the element plus whoever points at it, and `--depth 0` must not quietly
    mean the same as the default."""

    view = neighbourhood(clean, "component:cancellation", depth=0)

    assert view.outgoing == ()
    assert view.incoming != ()


def test_depth_three_reaches_a_third_hop(clean: Design) -> None:
    """The budget decrements once per level, not once per two: the seam that
    `orders` provides right back gets its own outgoing edges at the third
    hop. The cycle makes this the sharp end of the depth arithmetic — one
    level early or late and the fringe moves."""

    view = neighbourhood(clean, "seam:order-events", depth=3)

    provides = view.outgoing[0].deeper[1]
    assert (provides.field, provides.other.id) == ("provides", "seam:order-events")
    assert [hop.other.id for hop in provides.deeper] == [
        "component:orders",
        "component:cancellation",
        "data:order",
    ]


def test_the_inbound_side_stays_one_hop_at_any_depth(clean: Design) -> None:
    """A depth that deep would find more if the inbound side expanded too —
    `story:cancel-order` is satisfied by nothing here, but `seam:order-events`
    is pointed at by three elements whose own refs go further out."""

    view = neighbourhood(clean, "seam:order-events", depth=5)

    assert [(link.field, link.other.id) for link in view.incoming] == [
        ("touches", "story:cancel-order"),
        ("consumes", "component:cancellation"),
        ("provides", "component:orders"),
    ]


def test_a_dangling_ref_resolves_to_no_neighbour() -> None:
    design = resolve(load_store(FIXTURES / "broken"))

    view = neighbourhood(design, "component:dangling", depth=2)

    # `dangling`'s one ref is `contains: component:ghost`, which no file
    # defines: it must not appear as a neighbour, and the empty view is still
    # a successful one — `ab show` reports neighbourhoods, `ab check` reports
    # the ghost.
    assert view.outgoing == ()


def test_json_carries_the_full_view_and_the_body_flag(clean: Design) -> None:
    view = neighbourhood(clean, "requirement:cancel-orders", depth=2)

    with_body = view.render_json(include_body=True)
    without_body = view.render_json(include_body=False)

    assert with_body["schema_version"] == SCHEMA_VERSION
    assert with_body["element"]["body"].startswith("A customer may cancel")
    assert "body" not in without_body["element"]
    hop = with_body["points_at"][0]
    assert hop["field"] == "realized_by"
    assert hop["target"]["id"] == "component:cancellation"
    # Neighbours carry their fields but never prose or provenance: the body is
    # the focus element's, and where a neighbour lives is `source`'s story.
    assert "body" not in hop["target"]
    assert "source" not in hop["target"]
    assert [(deeper["field"], deeper["target"]["id"]) for deeper in hop["deeper"]] == [
        ("consumes", "seam:order-events")
    ]
    assert hop["deeper"][0]["deeper"] == []
    assert [(link["field"], link["source"]["id"]) for link in with_body["referenced_by"]] == [
        ("satisfies", "story:cancel-order"),
        ("realizes", "behavior:order-placed-v2"),
        ("realizes", "behavior:order-placed"),
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
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
        components=(
            Component(id="component:outsourced", title="Outsourced", state=State.DELEGATED),
        ),
    )

    (only,) = worklist(design, today=TODAY)

    assert only.element.id == "component:outsourced"
    assert only.reasons == ("state=delegated", "unowned")


def test_worklist_questions_turn_overdue_strictly_after_their_due_date() -> None:
    """A question due today is still open — the day itself is inside the ask,
    the same strict comparison `check` spells for expiry — and a question a
    decision has already resolved is nobody's worklist entry, whatever its
    state says."""
    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
        questions=(
            Question(id="question:today", title="Today", owner="a", due_on=TODAY),
            Question(
                id="question:yesterday",
                title="Yesterday",
                owner="a",
                due_on=TODAY - timedelta(days=1),
            ),
            Question(
                id="question:closed",
                title="Closed",
                owner="a",
                state=State.SPECIFIED,
                due_on=TODAY - timedelta(days=1),
                resolved_by="decision:done",
            ),
        ),
    )

    by_id = {gap.element.id: gap for gap in worklist(design, today=TODAY)}

    assert by_id["question:today"].reasons == ("state=unknown", "question-open")
    assert by_id["question:yesterday"].reasons == ("state=unknown", "question-overdue")
    # The date the reason hangs on travels with the entry, past or not.
    assert by_id["question:today"].due_on == TODAY
    assert by_id["question:yesterday"].due_on == TODAY - timedelta(days=1)
    assert "question:closed" not in by_id


def test_worklist_expires_an_external_strictly_after_its_expiry_date() -> None:
    """`expires_on` means "after this, re-check": the day itself is still
    trusted — `absicht.check`'s reading, and necessarily this one's too,
    because the worklist reuses that module's one spelling of "expired"
    rather than re-deriving the comparison."""
    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
        externals=(
            External(
                id="external:today",
                title="Today",
                state=State.SPECIFIED,
                owner="ops",
                external_kind=ExternalKind.SERVICE,
                expires_on=TODAY,
            ),
            External(
                id="external:yesterday",
                title="Yesterday",
                state=State.SPECIFIED,
                owner="ops",
                external_kind=ExternalKind.SERVICE,
                expires_on=TODAY - timedelta(days=1),
            ),
        ),
    )

    (only,) = worklist(design, today=TODAY)

    assert only.element.id == "external:yesterday"
    assert only.reasons == ("external-expired",)
    assert only.expires_on == TODAY - timedelta(days=1)


def test_worklist_gaps_a_behavior_with_no_observations() -> None:
    """The query-side twin of `policy/behavior-needs-observations`: the
    expectation with nothing observable is unfinished whatever its state —
    a `specified` behavior lands on the worklist for that reason alone."""
    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
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
    ownerless referencer means it does not. `component:deep`'s only referencer
    is the ownerless `requirement:mid`, whose own inherited owner (platform,
    via `story:top`) is never chained on: one level, no deeper."""
    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
        components=(
            Component(id="component:watched", title="Watched"),
            Component(id="component:owned", title="Owned", owner="qa"),
            Component(id="component:contested", title="Contested"),
            Component(id="component:deep", title="Deep"),
        ),
        requirements=(
            Requirement(
                id="requirement:carrier",
                title="Carrier",
                state=State.SPECIFIED,
                owner="platform",
                realized_by=("component:watched", "component:owned", "component:contested"),
            ),
            Requirement(
                id="requirement:rival",
                title="Rival",
                state=State.SPECIFIED,
                owner="rival-team",
                realized_by=("component:contested",),
            ),
            Requirement(id="requirement:mid", title="Mid", realized_by=("component:deep",)),
        ),
        stories=(
            Story(
                id="story:top",
                title="Top",
                state=State.SPECIFIED,
                owner="platform",
                satisfies=("requirement:mid",),
            ),
        ),
    )

    by_id = {gap.element.id: gap for gap in worklist(design, today=TODAY)}

    assert by_id["component:watched"].owner_inherited == "platform"
    assert by_id["component:watched"].reasons == ("state=unknown",)
    assert by_id["component:owned"].owner_inherited is None
    assert by_id["component:owned"].reasons == ("state=unknown",)
    assert by_id["component:contested"].owner_inherited is None
    assert by_id["component:contested"].reasons == ("state=unknown", "unowned")
    assert by_id["requirement:mid"].owner_inherited == "platform"
    assert by_id["component:deep"].owner_inherited is None
    assert by_id["component:deep"].reasons == ("state=unknown", "unowned")


# --- observations in the show view ----------------------------------------------


def test_the_effective_timing_follows_the_resource_kind_when_unsaid() -> None:
    """§1.2's table, as the show view spells it: an authored timing wins, an
    unsaid one follows what `at` resolved to — a stream defaults eventual,
    everything else immediate — and `must_not` has no timing to render, at
    no point having no when."""
    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
        components=(Component(id="component:c", title="C", state=State.SPECIFIED, owner="a"),),
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
    """`broken/`'s `contains` cycle is the input the walk must survive: the
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
        (("contains", False, "component:loop-b"),),
        (("contains", True, "component:loop-b"),),
    ]
    assert result.cycle_hit is True


def test_an_unknown_to_ref_raises_rather_than_answering_empty(clean: Design) -> None:
    """`ab trace` maps this to `USAGE`: "no path to a nonexistent element" is
    not an answer anyone should be able to mistake for a route check."""
    with pytest.raises(UnknownRefError, match="decision:never"):
        trace_paths(clean, "requirement:cancel-orders", to="decision:never-made")


# --- the packet document -------------------------------------------------------------


def _packet_document() -> str:
    """One packet exercising everything `clean/`'s milestone leaves empty: two
    scope blocks (one with prose), a ring element, every obligation list
    carrying content, and a criterion with a two-line `given`.

    Built by hand rather than assembled, because what is under test is the
    rendering of the model, not the selection that fills it — and a packet that
    silently dropped its `must_hold` ADRs or an element's prose passes every
    fixture-driven test the CLI modules run."""
    return packet_markdown(
        Packet(
            milestone="milestone:m",
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
                    ref="seam:edge",
                    fidelity=Fidelity.CONTRACT,
                    element={"id": "seam:edge", "title": "Edge"},
                ),
            ),
            must_hold=("decision:adr", "nfr:latency"),
            may_decide=("the retry policy",),
            unresolved=("question:q",),
            rejections=("rejection:big-bang",),
            criteria=(
                Criterion(
                    id="story:s#ac-1",
                    given=("a user", "an order"),
                    when="the user cancels",
                    then=("it works",),
                ),
                Criterion(
                    id="story:s#ac-2", kind=CriterionKind.STRUCTURAL, statement="one seam only"
                ),
            ),
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
    assert "- `seam:edge` — Edge" in document
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
    # A two-line given joins with ", "; a structural criterion carries its
    # statement under its kind.
    assert "given a user, an order; when the user cancels; then it works" in document
    assert "(structural) — one seam only" in document


def test_packet_markdown_drops_the_dash_when_the_outcome_is_empty() -> None:
    """No outcome, no hanging `—`: the identity line is the bare ref, and a
    scope-less milestone still spells the section rather than vanishing."""
    document = packet_markdown(
        Packet(
            milestone="milestone:m",
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
    without expanding it, and a must-not-break observation with no timing to
    spell. Built by hand like `_packet_document`, for the same reason: what is
    under test is the rendering of the model, not the selection that fills it."""

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
            },
        )

    return Packet(
        milestone="milestone:m",
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
                element={"id": "component:core", "title": "Core"},
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
                "behavior:guard",
                "The guard holds",
                [
                    observation(
                        "behavior:guard#obs-1", "Nothing leaks", "resource:log", "must_not", None
                    )
                ],
            ),
        ),
        satisfy=("behavior:a",),
        must_not_break=("behavior:guard",),
    )


def test_packet_markdown_separates_the_two_behavior_lists() -> None:
    document = packet_markdown(_behavior_packet())

    satisfy_at = document.index("## Behaviors to satisfy")
    not_break_at = document.index("## Behaviors that must not break")
    # Two clearly separated sections, the work before the guardrails.
    assert satisfy_at < not_break_at
    satisfy_section = document[satisfy_at:not_break_at]
    # The satisfy block with its observations, the effective timing spelled so
    # the agent never computes a default.
    assert "### A happens" in satisfy_section
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
    assert "standing expectations" in not_break_section
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

    # B joins under the behavior that composes it, observations included.
    assert "#### Composes: `behavior:b` — B happens" in document
    assert "- `behavior:b#obs-1` — B makes C occur (must, eventual, at behavior:c)" in document
    # C stays what that observation references — expanded nowhere.
    assert "Composes: `behavior:c`" not in document


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
    assert len(first) == 18  # fifteen element pages, index, traceability, gaps


def test_the_change_detection_notices_edits_additions_and_removals(tmp_path: Path) -> None:
    """The poll loop's whole judgement in one pair of functions, decoupled from
    the loop: docs/tasks/26-render-site.md asks for exactly this unit test
    instead of a timing-dependent one on the server itself."""

    store = tmp_path / "store"
    (store / "requirements").mkdir(parents=True)
    element = store / "requirements" / "r.md"
    element.write_text("---\nid: requirement:r\n---\n", encoding="utf-8")

    before = store_snapshot(store)
    assert not store_changed(store, before)

    # A touch far from any plausible real mtime, so the verdict is the
    # detection's, not the filesystem's.
    os.utime(element, ns=(2**40, 2**40))
    assert store_changed(store, before)

    (store / "system.yaml").write_text("id: system:s\n", encoding="utf-8")
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
