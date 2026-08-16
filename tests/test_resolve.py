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
"""

from __future__ import annotations

from pathlib import Path

import pytest

from absicht.load import load_store
from absicht.models import Component, Design, Requirement, Story, System
from absicht.resolve import Index, Reference, ResolveError, iter_references, resolve

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
        "decisions": 1,
        "milestones": 1,
    },
    "brownfield": {"requirements": 1, "stories": 1, "components": 2, "data": 1},
    "broken": {"externals": 1, "stories": 1, "components": 3, "decisions": 1, "questions": 1},
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

    assert len(index.by_id) == 11  # the system plus ten elements
    assert index.by_id["system:acme"] is design.system
    assert index.by_id["seam:order-events"] is design.seams[0]


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
