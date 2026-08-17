"""``absicht.resolve``: fold a ``LoadedStore`` into the ``Design`` artifact, plus the lookups every query command shares.

What these tests pin, per ``docs/tasks/03-resolve.md``:

- ``resolve`` over each fixture system produces the ``Design`` with the
  element counts that fixture was authored to have, and refuses —
  ``ResolveError``, never a partial ``Design`` — a store whose ``system.yaml``
  is missing or unreadable. ``broken/`` does not exercise that case (its
  defects are design-shaped, and its ``system.yaml`` parses), so the refusal
  gets its own two-file store.
- The reference index is built by walking the annotations in ``models.py``,
  not a hand-copied field list (the spec's own list already misses
  ``Rejection.milestone`` and ``Milestone.unresolved``, which is why it warns
  the list will drift): a ``Requirement.realized_by`` arrives as an incoming
  reference on the component, a criterion's ``touches`` is attributed to the
  story that carries it, and a dangling target is simply absent from the
  index rather than an error — turning a dangling ref into a finding is
  ``check``'s job, and it reads the same ``iter_references`` enumeration.
- ``orphaned()`` is the literal definition — ids with no entry in
  ``referenced_by`` — which includes the ``system`` element: it is the root
  of a design, nothing points at the root, and the one caller the spec names
  (``ab list --orphaned``) always passes a kind.

Since the model addendum (``docs/tasks/56-derived-scope-composition.md``):
the three computed facts §4/§5 insist are never stored — a behavior's scope,
the composition edges in both directions, and the supersession reverse edge
— each derived in exactly one place here, so ``show``, ``list``, ``packet``
and ``verify`` all read the same answer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from absicht.load import load_store
from absicht.models import (
    Behavior,
    Component,
    Design,
    Observation,
    Requirement,
    Scope,
    State,
    Story,
    System,
)
from absicht.resolve import (
    Index,
    Reference,
    ResolveError,
    composed_by,
    composes,
    inherited_owners,
    iter_references,
    resolve,
    scope_of,
    superseded_by,
    touches,
)

FIXTURES = Path(__file__).parent / "fixtures" / "systems"

# Only the kinds a fixture populates; every other kind tuple on `Design` must
# come back empty, which the counts test enforces via `.get(kind, 0)`.
EXPECTED_COUNTS: dict[str, dict[str, int]] = {
    "clean": {
        "requirements": 2,
        "stories": 1,
        "components": 3,
        "seams": 1,
        "data": 1,
        "resources": 1,
        "behaviors": 3,
        "decisions": 1,
        "milestones": 1,
    },
    "brownfield": {
        "requirements": 1,
        "stories": 1,
        "components": 2,
        "data": 1,
        "externals": 1,
        "behaviors": 1,
        "questions": 2,
        "milestones": 1,
    },
    "broken": {
        "externals": 1,
        "requirements": 1,
        "stories": 1,
        "components": 3,
        "seams": 1,
        "resources": 1,
        "behaviors": 8,
        "decisions": 1,
        "questions": 1,
        "milestones": 1,
    },
    "composite": {"externals": 1, "components": 2, "seams": 1, "data": 1},
}


@pytest.mark.parametrize("name", sorted(EXPECTED_COUNTS))
def test_each_fixture_resolves_to_its_expected_counts(name: str) -> None:
    design = resolve(load_store(FIXTURES / name))

    assert design.system is not None
    expected = EXPECTED_COUNTS[name]
    for kind in Design.model_fields:
        if kind in ("schema_version", "system"):
            continue
        assert len(getattr(design, kind)) == expected.get(kind, 0), kind


def test_a_store_without_a_system_cannot_resolve(tmp_path: Path) -> None:
    """Elements that loaded fine are not enough: a `Design` is built around
    its `System` element, and inventing a placeholder system would quietly
    change what every downstream command reports on."""

    store = tmp_path / "store"
    (store / "components").mkdir(parents=True)
    (store / "components" / "kept.md").write_text(
        "---\nid: component:kept\ntitle: Kept\n---\n", encoding="utf-8"
    )

    with pytest.raises(ResolveError, match=r"system\.yaml"):
        resolve(load_store(store))


def test_by_id_holds_every_element_including_the_system() -> None:
    design = resolve(load_store(FIXTURES / "clean"))

    index = Index.from_design(design)

    assert len(index.by_id) == 15  # the system plus fourteen elements
    assert index.by_id["system:acme"] is design.system
    assert index.by_id["seam:order-events"] is design.seams[0]
    # Behaviors load in filename order: `catalog-browsable.md` first, then
    # `order-placed-v2.md` before `order-placed.md`.
    assert index.by_id["behavior:catalog-browsable"] is design.behaviors[0]
    assert index.by_id["behavior:order-placed-v2"] is design.behaviors[1]


def test_referenced_by_finds_the_requirement_behind_a_component() -> None:
    index = Index.from_design(resolve(load_store(FIXTURES / "clean")))

    assert (
        Reference(
            source="requirement:cancel-orders", field="realized_by", target="component:cancellation"
        )
        in index.referenced_by["component:cancellation"]
    )


def test_a_criterion_touch_is_indexed_against_its_story() -> None:
    """A criterion is nested in `Story.acceptance` and its id is a
    `CriterionId`, not a `Ref`: its `touches` are attributed to the story that
    carries it, so every id the index deals in is one `by_id` can resolve."""

    index = Index.from_design(resolve(load_store(FIXTURES / "clean")))

    assert (
        Reference(source="story:cancel-order", field="touches", target="seam:order-events")
        in index.referenced_by["seam:order-events"]
    )


def test_a_behaviors_refs_and_observations_are_indexed_under_it() -> None:
    """An observation is to a behavior what a criterion is to a story: a
    nested record whose one ref (`at`) is attributed to the element that
    carries it. `iter_references` must therefore yield a behavior's `realizes`
    and `supersedes`, then every observation's `at`, with the behavior as
    source — which is also what lets the generic dangling-ref rule and the
    index's reverse lookups cover observation refs for free."""

    design = resolve(load_store(FIXTURES / "clean"))
    index = Index.from_design(design)

    assert index.references_from["behavior:order-placed-v2"] == (
        Reference(
            source="behavior:order-placed-v2", field="realizes", target="requirement:cancel-orders"
        ),
        Reference(
            source="behavior:order-placed-v2", field="supersedes", target="behavior:order-placed"
        ),
        Reference(source="behavior:order-placed-v2", field="at", target="resource:order-cache"),
        Reference(source="behavior:order-placed-v2", field="at", target="component:orders"),
        Reference(source="behavior:order-placed-v2", field="at", target="resource:order-cache"),
        Reference(source="behavior:order-placed-v2", field="at", target="behavior:order-placed"),
        Reference(source="behavior:order-placed-v2", field="at", target="component:orders"),
    )
    # The reverse side: both edges onto the superseded behavior, and the
    # observations' targets reachable from the resource.
    assert index.referenced_by["behavior:order-placed"] == (
        Reference(
            source="behavior:order-placed-v2", field="supersedes", target="behavior:order-placed"
        ),
        Reference(source="behavior:order-placed-v2", field="at", target="behavior:order-placed"),
    )
    assert index.referenced_by["resource:order-cache"] == (
        Reference(source="behavior:order-placed-v2", field="at", target="resource:order-cache"),
        Reference(source="behavior:order-placed-v2", field="at", target="resource:order-cache"),
        Reference(source="behavior:order-placed", field="at", target="resource:order-cache"),
    )


def test_a_dangling_target_is_absent_from_the_index_not_an_error() -> None:
    """`broken/`'s `component:dangling` points at `component:ghost`, which no
    file defines: the index must not raise, and the ghost must have no entry —
    while the edge itself stays enumerable, because `check`'s dangling-ref
    rule reads `iter_references` instead of re-walking `models.py`."""

    design = resolve(load_store(FIXTURES / "broken"))
    index = Index.from_design(design)

    assert "component:ghost" not in index.referenced_by
    assert Reference(
        source="component:dangling", field="contains", target="component:ghost"
    ) in tuple(iter_references(design))


def test_references_from_lists_outgoing_edges_in_field_order() -> None:
    """The mirror of `referenced_by`, which `ab show` walks for "what it points
    at": one entry per outgoing edge, in the model's field declaration order —
    the order the whole index is deterministic in."""

    index = Index.from_design(resolve(load_store(FIXTURES / "clean")))

    assert index.references_from["component:orders"] == (
        Reference(source="component:orders", field="contains", target="component:catalog"),
        Reference(source="component:orders", field="provides", target="seam:order-events"),
        Reference(source="component:orders", field="owns_data", target="data:order"),
    )


def test_references_from_keeps_a_dangling_edge_for_check_to_report() -> None:
    """The one asymmetry with `referenced_by`: a source is always an element,
    so an outgoing edge exists even when its target does not. Dropping it here
    would hide the ghost from every future consumer of the index, while
    `referenced_by` cannot hold it — nothing was pointed at."""

    index = Index.from_design(resolve(load_store(FIXTURES / "broken")))

    assert (
        Reference(source="component:dangling", field="contains", target="component:ghost")
        in index.references_from["component:dangling"]
    )


def test_orphaned_reports_the_one_element_nothing_points_at() -> None:
    design = Design(
        system=System(id="system:tiny", title="Tiny"),
        stories=(Story(id="story:s", title="S", satisfies=("requirement:r",)),),
        components=(
            Component(id="component:kept", title="Kept"),
            Component(id="component:loner", title="Loner"),
        ),
        requirements=(Requirement(id="requirement:r", title="R", realized_by=("component:kept",)),),
    )

    index = Index.from_design(design)

    # Every finite design has unreferenced sources — here the story no
    # milestone includes — and the system is the root, so pointing at it is
    # nobody's job either. The kind filter is what isolates the one genuine
    # orphan `ab list --orphaned` exists to surface.
    assert index.orphaned() == ("system:tiny", "story:s", "component:loner")
    assert index.orphaned("component") == ("component:loner",)


def test_inherited_owners_is_section_sevens_rule_over_the_index() -> None:
    """The §7 map `ab gaps` and `ab list --owner` both read: an unowned
    `unknown` inherits the owner of the single element referencing it — one
    level (a referencer's own inherited owner is never chained on), never
    stored. An own owner, a second referencing owner, an ownerless
    referencer, or a finished state means no entry."""
    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED, owner="a"),
        components=(
            Component(id="component:watched", title="Watched"),
            Component(id="component:owned", title="Owned", owner="qa"),
            Component(id="component:contested", title="Contested"),
            Component(id="component:deep", title="Deep"),
            # A finished unknown: inheritance is §7's rule about *unknowns*,
            # and an `observed` element does not acquire an owner by it.
            Component(id="component:seen", title="Seen", state=State.OBSERVED),
        ),
        requirements=(
            Requirement(
                id="requirement:carrier",
                title="Carrier",
                state=State.SPECIFIED,
                owner="platform",
                realized_by=(
                    "component:watched",
                    "component:owned",
                    "component:contested",
                    "component:seen",
                ),
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

    index = Index.from_design(design)

    assert inherited_owners(index) == {
        "component:watched": "platform",  # exactly one referencing owner
        "requirement:mid": "platform",  # ditto, through the story
    }
    # component:owned carries qa; :contested has two referencing owners;
    # :seen is observed, not unknown; :deep's only referencer (requirement:mid)
    # has no owner of its own, and mid's inherited one is not chained on.


# --- the addendum's derived behavior facts (§4.1, §4.2, §5) ----------------------


def _behavior(design: Design, ref: str) -> Behavior:
    """The fixture's behavior by id — narrowed once for the derived-fact
    tests, which all speak in behavior terms."""
    return next(behavior for behavior in design.behaviors if behavior.id == ref)


def test_touches_is_the_deduplicated_id_ordered_union_of_at_refs() -> None:
    """§4.1's primitive: the union of a behavior's observations' `at` refs —
    five observations collapsing to three targets, id-ordered though the file
    authored them resource-first. Composition targets ride along (they are
    `at` refs) but never expand, which is why the store's own order does not
    survive into the derived tuple."""
    design = resolve(load_store(FIXTURES / "clean"))

    replacement = _behavior(design, "behavior:order-placed-v2")

    assert touches(replacement) == (
        "behavior:order-placed",
        "component:orders",
        "resource:order-cache",
    )


def test_scope_is_local_for_exactly_one_component_and_nothing_else() -> None:
    """§4.1's classification over the shared fixtures: one component and
    nothing else — no resource, no seam, no second component — is `local`
    (`catalog-browsable` watches `component:catalog` alone). Everything else
    is `system`: a component beside a resource (`order-placed-v2`), a
    resource with no component at all (`order-placed`), composition-only
    observations (`broken`'s loop side — a behavior is not a component), and
    nothing observed anywhere (`broken`'s `no-observations`, which the policy
    rule already flags)."""
    clean = resolve(load_store(FIXTURES / "clean"))
    broken = resolve(load_store(FIXTURES / "broken"))

    assert scope_of(_behavior(clean, "behavior:catalog-browsable")) is Scope.LOCAL
    assert scope_of(_behavior(clean, "behavior:order-placed-v2")) is Scope.SYSTEM
    assert scope_of(_behavior(clean, "behavior:order-placed")) is Scope.SYSTEM
    assert scope_of(_behavior(broken, "behavior:compose-loop-a")) is Scope.SYSTEM
    assert scope_of(_behavior(broken, "behavior:no-observations")) is Scope.SYSTEM


def test_a_second_components_observation_flips_local_to_system() -> None:
    """The addendum's own motivating sentence: a behavior that grows an
    observation on a second component becomes a system behavior with no edit
    to say so. The two records differ by exactly that one observation."""
    one_component = Behavior(
        id="behavior:flips",
        title="Flips",
        trigger="Something happens.",
        observations=(
            Observation(id="behavior:flips#obs-1", statement="It lands", at="component:one"),
        ),
    )
    two_components = Behavior(
        id="behavior:flips",
        title="Flips",
        trigger="Something happens.",
        observations=(
            Observation(id="behavior:flips#obs-1", statement="It lands", at="component:one"),
            Observation(id="behavior:flips#obs-2", statement="It echoes", at="component:two"),
        ),
    )

    assert scope_of(one_component) is Scope.LOCAL
    assert scope_of(two_components) is Scope.SYSTEM


def test_superseded_by_derives_the_reverse_edge_without_storing_it() -> None:
    """§5: supersession is recorded on the replacement (`supersedes`) and
    mirrored nowhere — the superseded side's file authors no such key, and
    the index answers the reverse edge anyway."""
    index = Index.from_design(resolve(load_store(FIXTURES / "clean")))

    source = (FIXTURES / "clean" / "behaviors" / "order-placed.md").read_text(encoding="utf-8")
    assert "superseded_by" not in source

    assert superseded_by(index, "behavior:order-placed") == ("behavior:order-placed-v2",)


def test_a_supersession_chain_answers_one_hop_each(tmp_path: Path) -> None:
    """Two supersessions in a row — c replaces b, b replaces a — answer one
    hop each: a's superseder is b alone, never c transitively, the same
    one-hop discipline §4.2 pins for composition."""
    index = Index.from_design(resolve(load_store(_chain_store(tmp_path))))

    assert superseded_by(index, "behavior:a") == ("behavior:b",)
    assert superseded_by(index, "behavior:b") == ("behavior:c",)


def test_composed_by_is_the_exact_inverse_of_composes() -> None:
    """§4.2's two directions over the clean fixture: every composed target's
    `composed_by` names its composor back, and nothing appears in
    `composed_by` that does not compose it — the exact inverse, both ways."""
    design = resolve(load_store(FIXTURES / "clean"))
    index = Index.from_design(design)

    edges = {
        (behavior.id, target) for behavior in design.behaviors for target in composes(behavior)
    }
    reverse = {
        (composor, target)
        for target in {edge[1] for edge in edges}
        for composor in composed_by(index, target)
    }

    assert edges == reverse
    assert composed_by(index, "behavior:order-placed") == ("behavior:order-placed-v2",)


def test_observing_a_component_is_not_composing() -> None:
    """`composed_by` answers §4.2's behavior-to-behavior edges only: two of
    `order-placed-v2`'s observations watch `component:orders`, and neither is
    composition — an `at` edge onto a non-behavior is an observation, not a
    composition edge."""
    index = Index.from_design(resolve(load_store(FIXTURES / "clean")))

    assert composed_by(index, "component:orders") == ()


def test_the_derived_walks_stay_one_hop_on_cyclic_fixtures() -> None:
    """`broken`'s cycles are findings — 54's rules report them — but the
    derived facts must still answer rather than hang: each loop side gets its
    one-hop facts, because the walks read direct edges and never traverse.
    The visited-set discipline `trace` needs is, here, no traversal at all."""
    design = resolve(load_store(FIXTURES / "broken"))
    index = Index.from_design(design)

    assert composes(_behavior(design, "behavior:compose-loop-a")) == ("behavior:compose-loop-b",)
    assert composed_by(index, "behavior:compose-loop-b") == ("behavior:compose-loop-a",)
    assert superseded_by(index, "behavior:supersede-a") == ("behavior:supersede-b",)
    assert superseded_by(index, "behavior:supersede-b") == ("behavior:supersede-a",)


def test_a_composed_behaviors_touches_stay_its_own(tmp_path: Path) -> None:
    """The one-hop discipline applied to scope (§4.1): `chainer` observes
    only `behavior:chained`, and `chained`'s own observation of
    `component:one` stays chained's — `chainer`'s touches name the behavior
    alone, and nothing observed directly is system, not the component's
    local."""
    design = resolve(load_store(_chain_store(tmp_path)))

    chainer = _behavior(design, "behavior:chainer")

    assert touches(chainer) == ("behavior:chained",)
    assert scope_of(chainer) is Scope.SYSTEM


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _chain_store(tmp_path: Path) -> Path:
    """The two chains no shared fixture spells: supersession three deep (c
    replaces b replaces a) and composition one hop (chainer observes chained,
    chained observes a component). Growing `clean` instead would move other
    tickets' exact-count and snapshot assertions, so the chains get a store
    of their own — the same call the §7 inheritance fixture makes in
    `test_list_cli.py`."""
    root = tmp_path / "chain"
    _write(root, "system.yaml", "id: system:chain\ntitle: Chain\nstate: specified\n")
    _write(root, "components/one.md", "---\nid: component:one\ntitle: One\nstate: specified\n---\n")
    _write(
        root,
        "behaviors/a.md",
        "---\nid: behavior:a\ntitle: A\nstate: specified\ntrigger: A happens.\n"
        "observations:\n- id: behavior:a#obs-1\n  statement: A is observable\n"
        "  at: component:one\n---\n",
    )
    _write(
        root,
        "behaviors/b.md",
        "---\nid: behavior:b\ntitle: B\nstate: specified\ntrigger: B happens.\n"
        "supersedes:\n- behavior:a\n"
        "observations:\n- id: behavior:b#obs-1\n  statement: B is observable\n"
        "  at: component:one\n---\n",
    )
    _write(
        root,
        "behaviors/c.md",
        "---\nid: behavior:c\ntitle: C\nstate: specified\ntrigger: C happens.\n"
        "supersedes:\n- behavior:b\n"
        "observations:\n- id: behavior:c#obs-1\n  statement: C is observable\n"
        "  at: component:one\n---\n",
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
