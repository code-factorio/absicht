"""The pinned diagram positions ``ab layout`` computes and ``ab render`` reads.

Positions are design data, not a rendering detail (docs/tasks/25-layout.md):
they live in the store as the ``layout.yaml`` singleton so a diagram is worth
building spatial memory on — the same element sits at the same place on every
build, whatever else changed.

The algorithm is a hand-rolled layered layout, and that is a deliberate call
rather than thrift. The alternative was ``networkx.spring_layout``, which
would pull NumPy in for a bar the spec itself sets at "stable and legible
enough for a generated diagram"; the graphs here are small and mostly
hierarchical via ``contains``, which a layered layout states directly.
Components are ranked by ``contains`` depth and spread along columns by a
depth-first walk of the ``contains`` forest in id order; seams sit one rank
below the deepest component, externals one below that, resources one below
the externals — the boundary the diagram's own shapes underline. Determinism
is by
construction — no iteration order a dict could choose differently, no clock —
and the only input beyond the graph is ``random.Random(seed)``, drawn once
per node in id order: that is what makes ``--seed`` honest (same seed, same
picture; another seed, a differently wobbled one) while the wobble stays far
too small to move a box anywhere near its neighbours.

This module owns reading and writing ``layout.yaml`` through the codec, the
same way ``absicht.init`` owns ``system.yaml``: the file is a singleton the
command produces, not an element collection ``absicht.load`` walks.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path

from absicht.codec import CodecError, dump_singleton, parse_singleton
from absicht.models import Design, Layout, Position, Ref

_LAYOUT_FILE = "layout.yaml"

_SPACING = 4.0
"""Distance between ranks and columns: wide enough that boxes, and the labels
`ab render` draws beside them, never collide."""

_JITTER = 0.5
"""The seed's reach: every node's coordinates wobble by at most this much,
an order of magnitude under `_SPACING` so the wobble can never stack a box
onto its neighbour."""


class LayoutError(Exception):
    """``layout.yaml`` could not be read: a statement about the store, not
    the invocation — the CLI maps it to ``FINDINGS``, like ``build`` maps
    load errors."""


def nodes(design: Design) -> tuple[Ref, ...]:
    """The diagram node set: components, seams, externals and resources, in
    id order.

    The same boxes `docs/tasks/27-render-diagrams.md` draws, no more: data
    entities and the prose kinds are not diagram nodes, and `--check` asks
    exactly "does every one of these have a position". Resources joined the
    set with `docs/tasks/60-addendum-render.md` — they are drawn at the
    boundary, outside the design boundary the addendum's §1 argues them into,
    and `ab layout` positions them like every other node because this one
    function is the whole node set.
    """
    return tuple(
        sorted(
            (
                *(component.id for component in design.components),
                *(seam.id for seam in design.seams),
                *(external.id for external in design.externals),
                *(resource.id for resource in design.resources),
            )
        )
    )


def compute(design: Design, *, seed: int = 0) -> Layout:
    """Fresh positions for every diagram node; the module docstring has the
    shape and the reasoning. Nothing here looks at a previous layout —
    keeping pinned positions is `merge`'s job, not the algorithm's."""
    # Wobble, not a secret: reproducibility is the requirement, and a
    # `random.Random` re-seeded from `--seed` is the documented same-seed,
    # same-sequence guarantee — nothing here must be unpredictable.
    rng = random.Random(seed)  # nosec B311
    wobble = {
        ref: (rng.uniform(-_JITTER, _JITTER), rng.uniform(-_JITTER, _JITTER))
        for ref in nodes(design)
    }
    columns, depths = _contains_columns(design)
    positions = [
        Position(
            ref=ref,
            x=columns[ref] * _SPACING + wobble[ref][0],
            y=depths[ref] * _SPACING + wobble[ref][1],
        )
        for ref in sorted(columns)
    ]
    seam_rank = max(depths.values(), default=-1) + 1
    positions += _row((seam.id for seam in design.seams), rank=seam_rank, wobble=wobble)
    positions += _row(
        (external.id for external in design.externals), rank=seam_rank + 1, wobble=wobble
    )
    # Resources take the outermost rank: outside the design boundary, past the
    # externals — the spatial form of addendum §1's argument, which the
    # diagram half of `ab render` underlines with their own shape.
    positions += _row(
        (resource.id for resource in design.resources), rank=seam_rank + 2, wobble=wobble
    )
    return Layout(positions=tuple(sorted(positions, key=lambda position: position.ref)))


def merge(existing: Layout, fresh: Layout) -> Layout:
    """`--recompute`: a pinned position wins, a missing one is filled.

    Every ref `existing` already positions keeps exactly that position —
    "stable layout" means a new component must not reshuffle the diagram —
    and only nodes without a pin take theirs from `fresh`. Entries for
    elements no longer in the design are kept too: layout never deletes,
    the same line `ab init` and `ab new` hold.
    """
    pinned = {position.ref: position for position in existing.positions}
    combined = {position.ref: position for position in fresh.positions} | pinned
    return Layout(positions=tuple(combined[ref] for ref in sorted(combined)))


def missing(design: Design, pinned: Layout) -> tuple[Ref, ...]:
    """Diagram nodes with no pinned position, in id order — the `--check` answer."""
    positioned = {position.ref for position in pinned.positions}
    return tuple(ref for ref in nodes(design) if ref not in positioned)


def read_layout(root: Path) -> Layout:
    """The store's pinned positions; no `layout.yaml` yet is an empty layout.

    A malformed file is a `LayoutError` rather than a silent empty layout:
    reading it as "nothing pinned yet" would throw away positions a human
    may have hand-tuned, which is exactly the data this command exists to
    keep.
    """
    path = root / _LAYOUT_FILE
    if not path.is_file():
        return Layout()
    try:
        return parse_singleton(path.read_text(encoding="utf-8"), model=Layout)
    except (CodecError, OSError) as exc:
        raise LayoutError(f"{_LAYOUT_FILE}: {exc}") from exc


def write_layout(root: Path, pinned: Layout) -> Path:
    """Write the singleton and return its path. The dump's field order is the
    model's, so two runs over the same input write the same bytes — the
    determinism promise, one layer down."""
    path = root / _LAYOUT_FILE
    path.write_text(dump_singleton(pinned), encoding="utf-8")
    return path


def _contains_columns(design: Design) -> tuple[dict[Ref, int], dict[Ref, int]]:
    """Column and depth per component, from a depth-first walk of the
    ``contains`` forest in id order.

    A component nothing contains is a root; children are visited in id
    order, so the same forest always yields the same columns. Whatever the
    walk cannot reach — a ``contains`` cycle, or a child whose parent is not
    a component in this design — is appended at depth 0 in id order:
    `check` is the layer that reports a broken graph, layout just has to
    place it deterministically anyway.
    """
    component_ids = {component.id for component in design.components}
    children = {
        component.id: tuple(sorted(child for child in component.contains if child in component_ids))
        for component in sorted(design.components, key=lambda component: component.id)
    }
    contained = {child for kids in children.values() for child in kids}
    columns: dict[Ref, int] = {}
    depths: dict[Ref, int] = {}

    def place(ref: Ref, depth: int) -> None:
        if ref in columns:
            return
        columns[ref] = len(columns)
        depths[ref] = depth
        for child in children[ref]:
            place(child, depth + 1)

    for root in sorted(ref for ref in children if ref not in contained):
        place(root, 0)
    for leftover in sorted(set(children) - set(columns)):
        place(leftover, 0)
    return columns, depths


def _row(
    refs: Iterable[Ref], *, rank: int, wobble: dict[Ref, tuple[float, float]]
) -> list[Position]:
    """One kind along a single rank, in id order — the flat rows of the
    layout: nothing in a seam or an external nests, so its place in the row
    is just its place in the id order."""
    return [
        Position(
            ref=ref,
            x=index * _SPACING + wobble[ref][0],
            y=rank * _SPACING + wobble[ref][1],
        )
        for index, ref in enumerate(sorted(refs))
    ]
