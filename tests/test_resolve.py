"""``absicht.resolve``: fold a store into a ``Design``, and index the graph.

The seam between "the store as files" and "the design as a graph", so what
these tests pin is what happens at that crossing and nowhere else:

- the fold moves every collection across untouched and revalidates. Unique
  ids and contract-only exports are only decidable once every file sits in
  one record, so a store that does not fold is refused whole — a partial
  ``Design`` would quietly change what every downstream command reports on.
  A store with no ``design.yaml`` is the same refusal for the same reason;
- the index is built by walking the annotations on the models, not a
  hand-copied field list that would go stale on the first new field: a
  component's ``parent`` and an observation's ``at`` arrive as labelled edges
  without anybody adding them, and an authored ``Relationship`` lands under
  its own type name so one walk sees one kind of edge;
- a dangling target keeps its outgoing edge and gains no incoming one. Making
  it an error is ``check``'s job, and dropping the edge here would hide the
  ghost from the rule that has to report it;
- the derived facts are derived in exactly one place — a behavior's reach,
  the composition edges in both directions, the supersession reverse edge and
  an observation's effective timing — so ``show``, ``list``, ``packet`` and
  ``verify`` all read the same answer;
- an import reaches the other design's ``exports`` and nothing else, which is
  the rule that lets two designs move apart at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from absicht.load import load_store
from absicht.models.design import (
    Behavior,
    Component,
    ComponentLevel,
    Design,
    Import,
    Interface,
    InterfaceStyle,
    Milestone,
    Observation,
    Outcome,
    QualityAttribute,
    QualityRequirement,
    RelationshipType,
    State,
    Timing,
)
from absicht.resolve import (
    COLLECTIONS,
    Index,
    Reference,
    ResolveError,
    Scope,
    composed_by,
    composes,
    effective_timing,
    inherited_owners,
    observed,
    resolve,
    scope_of,
    superseded_by,
    touches,
)

FIXTURES = Path(__file__).parent / "fixtures" / "systems"

# Each fixture's header, and how many addressable elements it folds to. The
# element count is the one number that spans every collection, so a kind that
# silently stopped folding shows up here rather than in whichever command
# happened to read it.
HEADERS: dict[str, tuple[str, str, str, int]] = {
    "clean": ("design:acme", "ACME orders", "1.0.0", 22),
    "brownfield": ("design:legacy", "Legacy billing", "0.4.0", 12),
    "broken": ("design:broken", "A store with one of everything wrong", "0.1.0", 22),
    "composite": ("design:acme-composite", "ACME, across two repositories", "2.1.0", 10),
}


@pytest.mark.parametrize("name", sorted(HEADERS))
def test_each_fixture_folds_into_the_design_its_header_names(name: str) -> None:
    """The fold is the header plus the walk, and nothing else: every
    collection arrives exactly as `load` read it, notes included — they ride
    on the `Design` without being elements, which the element count says."""

    loaded = load_store(FIXTURES / name)

    design = resolve(loaded)

    (design_id, title, version, elements) = HEADERS[name]
    assert (design.id, design.title, design.version) == (design_id, title, version)
    for collection in COLLECTIONS:
        assert getattr(design, collection) == getattr(loaded, collection), collection
    assert sum(1 for _ in design.elements()) == elements


def test_a_store_without_a_design_yaml_cannot_resolve(tmp_path: Path) -> None:
    """Elements that loaded fine are not enough: a design is built around its
    own id, title and version, and inventing a placeholder header would
    quietly change what every downstream command reports on."""

    _write(tmp_path, "components/kept.md", _component("component:kept", "Kept"))

    with pytest.raises(ResolveError, match=r"design\.yaml"):
        resolve(load_store(tmp_path))


def test_a_store_that_does_not_fold_into_one_design_is_refused(tmp_path: Path) -> None:
    """Why the fold revalidates instead of copying fields across: two files
    claiming one id are each fine on their own, and only the assembled record
    can see the clash. The refusal names it, so `check` has something to say."""

    _write(tmp_path, "design.yaml", _DESIGN)
    _write(tmp_path, "components/first.md", _component("component:twice", "First"))
    _write(tmp_path, "components/second.md", _component("component:twice", "Second"))

    with pytest.raises(ResolveError, match="duplicate id 'component:twice'"):
        resolve(load_store(tmp_path))


# ---------------------------------------------------------------- the index


def test_local_holds_every_element_of_the_design() -> None:
    index = Index(_design("clean"))

    assert len(index.local) == 22
    assert index.local["interface:order-events"].title == "Order events"
    # Behaviors load in filename order, so `order-placed-v2` precedes the
    # `order-placed` it replaces: `-` sorts before `.`.
    assert list(index.of_type(Behavior))[2].id == "behavior:order-placed-v2"


def test_an_authored_edge_is_indexed_under_its_own_type_name() -> None:
    """A `Relationship` is an edge like any other once it is in the index, so
    `trace` and `check` walk one kind of thing. The label is the edge type,
    which is what makes "why does this point here" answerable."""

    index = Index(_design("clean"))

    assert index.referenced_by("req:cancel-orders") == (
        Reference(source="behavior:order-cancelled", field="realizes", target="req:cancel-orders"),
        Reference(source="component:orders", field="implements", target="req:cancel-orders"),
    )


def test_references_from_lists_the_fields_first_then_the_authored_edges() -> None:
    """The mirror of `referenced_by`, which `ab show` walks for "what it points
    at": a field-borne link (`parent` has exactly one owner, so it stays a
    field) comes in model declaration order, and the file's `relates` block
    follows — the order the whole index is deterministic in."""

    index = Index(_design("clean"))

    assert index.references_from("component:orders") == (
        Reference(source="component:orders", field="parent", target="component:acme"),
        Reference(source="component:orders", field="implements", target="req:cancel-orders"),
        Reference(
            source="component:orders", field="constrained_by", target="constraint:gdpr-erasure"
        ),
        Reference(source="component:orders", field="depends_on", target="library:pydantic"),
        Reference(source="component:orders", field="depends_on", target="resource:order-cache"),
        Reference(source="component:orders", field="depends_on", target="resource:order-stream"),
    )


def test_an_observations_ref_is_attributed_to_the_behavior_that_carries_it() -> None:
    """An observation is a nested record whose id is not a `Ref`, so its one
    outgoing link is attributed to the behavior it is anchored to. That is
    what lets the generic dangling-ref rule and the reverse lookups cover an
    observation's `at` for free."""

    index = Index(_design("clean"))

    assert index.references_from("behavior:order-placed-v2") == (
        Reference(
            source="behavior:order-placed-v2", field="supersedes", target="behavior:order-placed"
        ),
        Reference(source="behavior:order-placed-v2", field="at", target="behavior:order-placed"),
        Reference(source="behavior:order-placed-v2", field="at", target="resource:order-stream"),
    )
    assert index.referenced_by("behavior:order-placed") == (
        Reference(
            source="behavior:order-placed-v2", field="supersedes", target="behavior:order-placed"
        ),
        Reference(source="behavior:order-placed-v2", field="at", target="behavior:order-placed"),
    )


def test_a_dangling_target_keeps_its_outgoing_edge_and_gains_no_incoming_one() -> None:
    """`broken/`'s `component:dangling` implements `req:ghost`, which no file
    defines. The index must not raise, the ghost must have no entry — nothing
    that exists was pointed at — and the edge itself must survive, because
    `check`'s dangling-ref rule is what reads it."""

    index = Index(_design("broken"))

    assert index.get("req:ghost") is None
    assert not index.resolves("req:ghost")
    assert index.referenced_by("req:ghost") == ()
    assert Reference(
        source="component:dangling", field="implements", target="req:ghost"
    ) in index.references_from("component:dangling")


def test_edges_answer_by_relationship_type() -> None:
    """The typed view every rule that branches on an edge kind reads: which
    pairs an edge type joins, and which ends take part in one."""

    index = Index(_design("clean"))

    assert list(index.edges(RelationshipType.IMPLEMENTS)) == [
        ("component:catalog", "req:browse-catalog"),
        ("component:orders", "req:cancel-orders"),
    ]
    assert index.targets_of(RelationshipType.REALIZES) == {
        "req:browse-catalog",
        "req:cancel-orders",
    }
    assert index.sources_of(RelationshipType.DEPENDS_ON) == {"component:orders"}


def test_orphaned_reports_the_ids_nothing_points_at() -> None:
    """The literal definition — no incoming edge — in `Design` field order.
    Every finite design has unreferenced sources, so the kind filter is what
    isolates the one genuine orphan `ab list --orphaned` exists to surface:
    `brownfield`'s audit log, which no component owns and no observation
    watches."""

    index = Index(_design("brownfield"))

    assert index.orphaned() == (
        "req:refund-parity",
        "data:audit-log",
        "question:nightly-retry",
    )
    assert index.orphaned("data") == ("data:audit-log",)


def test_inherited_owners_maps_an_unowned_unknown_to_its_one_referencing_owner() -> None:
    """The map `ab gaps` and `ab list --owner` both read: an unowned `unknown`
    inherits the owner of the single element referencing it, one level deep
    and never stored. An own owner, a second referencing owner, an ownerless
    referencer, or a finished state means no entry."""

    design = Design(
        id="design:tiny",
        title="Tiny",
        version="0.1.0",
        components=(
            _element(Component, "component:watched", "Watched"),
            _element(Component, "component:owned", "Owned", owner="qa"),
            _element(Component, "component:contested", "Contested"),
            _element(Component, "component:deep", "Deep"),
            # Its only referencer is `component:mid`, which carries no owner of
            # its own — an inherited one is never chained on.
            _element(Component, "component:mid", "Mid", parent="component:deep"),
            # A finished unknown: inheritance is a rule about *unknowns*, and
            # an `observed` element does not acquire an owner by it.
            _element(Component, "component:seen", "Seen", state=State.OBSERVED),
        ),
        qualities=(
            QualityRequirement(
                id="quality:rival",
                title="Rival",
                state=State.SPECIFIED,
                owner="rival-team",
                attribute=QualityAttribute.LATENCY,
                scope=("component:contested",),
            ),
        ),
        milestones=(
            Milestone(
                id="milestone:slice",
                title="Slice",
                state=State.SPECIFIED,
                owner="platform",
                scope=(
                    "component:watched",
                    "component:owned",
                    "component:contested",
                    "component:mid",
                    "component:seen",
                ),
            ),
        ),
    )

    assert inherited_owners(Index(design)) == {
        "component:watched": "platform",
        "component:mid": "platform",
    }


# ----------------------------------------------------------- what a behavior


def test_observed_is_the_deduplicated_id_ordered_union_of_at_refs() -> None:
    """The primitive the reach classification is built on: three observations
    authored component-first collapse to their targets in id order, so the
    store's own order never survives into a derived tuple."""

    behavior = _behavior(_design("clean"), "behavior:order-cancelled")

    assert observed(behavior) == (
        "component:orders",
        "resource:order-cache",
        "resource:order-stream",
    )


def test_touches_answers_whether_a_behavior_reaches_a_scope() -> None:
    """What `packet` asks of every active behavior: does this one watch
    anything the slice may change? A behavior that does not is not the
    milestone's business, and one that does cannot be broken by it."""

    behavior = _behavior(_design("clean"), "behavior:order-cancelled")

    assert touches(behavior, frozenset({"component:orders"}))
    assert touches(behavior, frozenset({"component:catalog", "resource:order-stream"}))
    assert not touches(behavior, frozenset({"component:catalog"}))


def test_scope_is_local_for_exactly_one_component_and_nothing_else() -> None:
    """One component and nothing else — no resource, no interface, no second
    component — is `local`. Everything else is `system`: a component beside a
    resource, composition-only observations (a behavior is not a component),
    and nothing observed anywhere."""

    clean = _design("clean")
    broken = _design("broken")

    assert scope_of(_behavior(clean, "behavior:catalog-browsable")) is Scope.LOCAL
    assert scope_of(_behavior(clean, "behavior:order-placed")) is Scope.LOCAL
    assert scope_of(_behavior(clean, "behavior:order-cancelled")) is Scope.SYSTEM
    assert scope_of(_behavior(clean, "behavior:order-placed-v2")) is Scope.SYSTEM
    assert scope_of(_behavior(broken, "behavior:compose-loop-a")) is Scope.SYSTEM
    assert scope_of(_behavior(broken, "behavior:no-observations")) is Scope.SYSTEM


def test_a_second_components_observation_flips_local_to_system() -> None:
    """The motivating sentence, held: a behavior that grows an observation on
    a second component becomes a system behavior with no edit to say so. The
    two records differ by exactly that one observation."""

    one_component = Behavior(
        id="behavior:flips",
        title="Flips",
        trigger="Something happens.",
        observations=(
            Observation(id="behavior:flips#obs-1", statement="It lands", at="component:one"),
        ),
    )
    two_components = one_component.model_copy(
        update={
            "observations": (
                *one_component.observations,
                Observation(id="behavior:flips#obs-2", statement="It echoes", at="component:two"),
            )
        }
    )

    assert scope_of(one_component) is Scope.LOCAL
    assert scope_of(two_components) is Scope.SYSTEM


@pytest.mark.parametrize(
    ("observation_id", "expected"),
    [
        ("behavior:order-cancelled#obs-1", Timing.IMMEDIATE),  # a component
        ("behavior:order-cancelled#obs-2", None),  # must_not: no when at all
        ("behavior:order-cancelled#obs-3", Timing.EVENTUAL),  # a stream
    ],
)
def test_effective_timing_resolves_through_whatever_at_names(
    observation_id: str, expected: Timing | None
) -> None:
    """The model answers this given a resource kind; the index is what turns
    an `at` ref into one. Both spellings are the same rule, so `packet` and
    `verify` cannot drift apart on when an expectation becomes true."""

    index = Index(_design("clean"))
    behavior = _behavior(index.design, "behavior:order-cancelled")
    (observation,) = [o for o in behavior.observations if o.id == observation_id]

    assert effective_timing(observation, index) is expected


def test_an_observation_on_a_ref_that_resolves_to_nothing_reads_immediate() -> None:
    """`broken/`'s ghost store: resolving to nothing yields no resource kind,
    and the default follows from that rather than from an exception. The
    dangling ref is `check`'s to report, not this walk's to trip over."""

    index = Index(_design("broken"))
    (observation,) = _behavior(index.design, "behavior:dangling-observation").observations

    assert observation.outcome is Outcome.MUST
    assert effective_timing(observation, index) is Timing.IMMEDIATE


# ------------------------------------------------- composition, supersession


def test_superseded_by_derives_the_reverse_edge_without_storing_it() -> None:
    """Supersession is recorded on the replacement and mirrored nowhere — the
    superseded side's file authors no such key, and the index answers the
    reverse edge anyway."""

    index = Index(_design("clean"))

    source = (FIXTURES / "clean" / "behaviors" / "order-placed.md").read_text(encoding="utf-8")
    assert "superseded_by" not in source

    assert superseded_by(index, "behavior:order-placed") == ("behavior:order-placed-v2",)


def test_a_supersession_chain_answers_one_hop_each(tmp_path: Path) -> None:
    """Two supersessions in a row — c replaces b, b replaces a — answer one
    hop each: a's superseder is b alone, never c transitively, the same
    one-hop discipline composition holds."""

    index = Index(resolve(load_store(_chain_store(tmp_path))))

    assert superseded_by(index, "behavior:a") == ("behavior:b",)
    assert superseded_by(index, "behavior:b") == ("behavior:c",)


def test_composed_by_is_the_exact_inverse_of_composes() -> None:
    """Both directions over the clean fixture: every composed target names its
    composer back, and nothing appears in `composed_by` that does not compose
    it — the exact inverse, both ways."""

    design = _design("clean")
    index = Index(design)

    edges = {
        (behavior.id, target) for behavior in design.behaviors for target in composes(behavior)
    }
    reverse = {
        (composer, target)
        for target in {edge[1] for edge in edges}
        for composer in composed_by(index, target)
    }

    assert edges == reverse
    assert composed_by(index, "behavior:order-placed") == ("behavior:order-placed-v2",)


def test_observing_a_component_is_not_composing() -> None:
    """`composed_by` answers behavior-to-behavior edges only: an `at` edge
    onto anything else is an observation, and the prefix guard is the
    definition rather than a filter bolted on."""

    index = Index(_design("clean"))

    assert composed_by(index, "component:orders") == ()


def test_the_derived_walks_stay_one_hop_on_cyclic_fixtures() -> None:
    """`broken/`'s cycles are findings for `check` to report, but the derived
    facts must still answer rather than hang: each loop side gets its one-hop
    facts, because the walks read direct edges and never traverse."""

    design = _design("broken")
    index = Index(design)

    assert composes(_behavior(design, "behavior:compose-loop-a")) == ("behavior:compose-loop-b",)
    assert composed_by(index, "behavior:compose-loop-b") == ("behavior:compose-loop-a",)
    assert superseded_by(index, "behavior:supersede-a") == ("behavior:supersede-b",)
    assert superseded_by(index, "behavior:supersede-b") == ("behavior:supersede-a",)


def test_a_composed_behaviors_reach_stays_its_own(tmp_path: Path) -> None:
    """The one-hop discipline applied to reach: `chainer` observes only
    `behavior:chained`, and `chained`'s own observation of `component:one`
    stays chained's. `chainer` names the behavior alone, and a behavior is not
    a component, so its reach is `system` rather than the component's local."""

    design = resolve(load_store(_chain_store(tmp_path)))

    chainer = _behavior(design, "behavior:chainer")

    assert observed(chainer) == ("behavior:chained",)
    assert scope_of(chainer) is Scope.SYSTEM


# ------------------------------------------------------------------ imports


def test_an_import_reaches_the_other_designs_exports_and_nothing_else() -> None:
    """The rule that lets two designs move apart at all: a foreign ref
    resolves only if the other design offered it. Everything unlisted is
    private, and the index says so by name — an id nobody exported is not a
    dangling ref, it is a boundary somebody crossed."""

    other = Design(
        id="design:payments",
        title="Payments",
        version="1.0.0",
        exports=("interface:charges",),
        components=(_element(Component, "component:ledger", "Ledger"),),
        interfaces=(Interface(id="interface:charges", title="Charges", style=InterfaceStyle.HTTP),),
    )
    mine = Design(
        id="design:mine",
        title="Mine",
        version="1.0.0",
        imports=(Import(id="design:payments", source="../payments"),),
    )

    index = Index(mine, {"design:payments": other})

    assert index.resolves("design:payments")
    assert index.resolves("interface:charges")
    assert index.get("interface:charges") is other.interfaces[0]
    assert not index.resolves("component:ledger")
    assert index.is_private_foreign("component:ledger")
    assert not index.is_private_foreign("component:nowhere")


# ------------------------------------------------------------------ helpers


_DESIGN = "id: design:tiny\ntitle: Tiny\nversion: 0.1.0\n"


def _design(name: str) -> Design:
    return resolve(load_store(FIXTURES / name))


def _behavior(design: Design, ref: str) -> Behavior:
    """The design's behavior by id — narrowed once for the derived-fact tests,
    which all speak in behavior terms."""
    return next(behavior for behavior in design.behaviors if behavior.id == ref)


def _element[T: Component](model: type[T], ref: str, title: str, **fields: object) -> T:
    return model(id=ref, title=title, level=ComponentLevel.CONTAINER, **fields)


def _component(ref: str, title: str) -> str:
    return f"---\nid: {ref}\ntitle: {title}\nlevel: container\n---\n"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _chain_store(tmp_path: Path) -> Path:
    """The two chains no shared fixture spells: supersession three deep (c
    replaces b replaces a) and composition one hop (chainer observes chained,
    chained observes a component). Growing `clean` instead would move other
    modules' exact-count and snapshot assertions, so the chains get a store of
    their own."""
    root = tmp_path / "chain"
    _write(root, "design.yaml", "id: design:chain\ntitle: Chain\nversion: 0.1.0\n")
    _write(root, "components/one.md", _component("component:one", "One"))
    for slug, supersedes in (("a", None), ("b", "behavior:a"), ("c", "behavior:b")):
        _write(
            root,
            f"behaviors/{slug}.md",
            f"---\nid: behavior:{slug}\ntitle: {slug.upper()}\nstate: specified\n"
            + (f"supersedes:\n- {supersedes}\n" if supersedes else "")
            + f"trigger: {slug.upper()} happens.\n"
            f"observations:\n- id: behavior:{slug}#obs-1\n"
            f"  statement: {slug.upper()} is observable\n  at: component:one\n---\n",
        )
    _write(
        root,
        "behaviors/chained.md",
        "---\nid: behavior:chained\ntitle: Chained\nstate: specified\ntrigger: Chained happens.\n"
        "observations:\n- id: behavior:chained#obs-1\n  statement: Chained is observable\n"
        "  at: component:one\n---\n",
    )
    _write(
        root,
        "behaviors/chainer.md",
        "---\nid: behavior:chainer\ntitle: Chainer\nstate: specified\ntrigger: Chainer happens.\n"
        "observations:\n- id: behavior:chainer#obs-1\n  statement: Chained occurs too\n"
        "  at: behavior:chained\n---\n",
    )
    return root
