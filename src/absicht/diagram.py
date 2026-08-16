"""The diagram half of ``ab render``: the design as boxes and edges.

A separate module rather than more of ``absicht.render`` because the two
halves share only their inputs — a resolved ``Design`` plus the pinned
``Layout`` — while their machinery is genuinely different (HTML pages versus
three diagram DSLs, a preview server versus one-shot files). It sits above
``render`` in the layer stack for the one thing they do share: the mermaid
emitter and its node keys, so ``ab trace``'s diagram and this one cannot
spell a node two ways.

Two rules shape everything here:

- **Pinned positions or refusal.** The coordinates come from
  ``layout.yaml`` and nowhere else — if a node has no pin, ``build`` raises
  rather than falling back to an auto-layout, because a diagram whose boxes
  move between builds never builds the spatial memory that pinning exists
  for (``docs/tasks/25-layout.md``'s whole argument).
- **Determinism by construction.** Nodes and edges walk in fixed orders,
  floats are emitted at two decimals, SVG element ids derive from refs, and
  every mapping is iterated sorted or in first-appearance order — so the
  same store spells byte-identical output, the property CI's determinism job
  cross-checks from a clean checkout (``docs/maintainers/verification.md``).

The colours follow the data-viz method this repo's diagrams hold themselves
to: categorical slots in a fixed order (never cycled), a chroma-less neutral
for "no signal", one ordinal blue ramp for churn's ordered buckets, and text
ink computed per fill by WCAG contrast. The state overlay's class set is the
``State`` enum and cannot be cut to the three classes that hold apart
pairwise everywhere, so an overlaid SVG also spells each box's class on the
box — the caption is the relief channel; the hue is the scan aid, never the
only carrier.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from pathlib import Path

from absicht.git import GitError, commit_count, repo_root
from absicht.layout import LayoutError, nodes, read_layout
from absicht.models import Component, Design, Element, Position, Ref, Seam, State
from absicht.render import UnknownRefError, mermaid, node_key
from absicht.resolve import Index, subtree

OVERLAYS = ("state", "milestone", "coverage", "churn")
"""The overlay vocabulary, the values ``ab render --overlay`` accepts. The
CLI owns the enum; this is the library's spelling of the same four words."""

# --- the palette -----------------------------------------------------------------
#
# Hex values from the validated reference instance of the data-viz method:
# nothing here is eyeballed. Light-surface values throughout — an emitted SVG
# pins its own light surface, so it reads the same wherever it is embedded;
# mermaid and d2 carry their ink alongside the fill for the same reason.

_NEUTRAL = "#f0efec"
"""No signal: deliberately chroma-less, the diverging midpoint's gray."""

_CATEGORICAL = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")
"""Categorical slots in the reference fixed order, never cycled. The first
three hold apart pairwise in any arrangement; the full five rely on the class
caption a coloured box also spells (see the module docstring)."""

_ORDINAL = ("#86b6ef", "#2a78d6", "#104281")
"""Churn's buckets as one blue ramp, light → dark as the change count grows —
an ordered dimension gets an ordered ramp, not more hues."""

_SURFACE = "#fcfcfb"
"""The SVG's own background: the file carries its surface with it."""

_FRAME = "#c3c2b7"
"""Box outlines and edge lines: recessive chrome, never a data colour."""

_STATE_FILL: Mapping[State, str] = {
    State.SPECIFIED: _CATEGORICAL[0],
    State.CONSTRAINED: _CATEGORICAL[1],
    State.DELEGATED: _CATEGORICAL[2],
    State.UNKNOWN: _CATEGORICAL[3],
    State.OBSERVED: _CATEGORICAL[4],
    # A decision not to build carries no completeness signal worth a hue.
    State.OUT_OF_SCOPE: _NEUTRAL,
}
"""States to slots in the enum's own declaration order — a state added later
takes the next slot, and one with no entry falls to the neutral below."""

_COVERED = _CATEGORICAL[0]
"""Coverage's filled side; the unfilled side is the neutral."""


# --- the picture -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Diagram:
    """The picture every format renders: the boxes ``ab layout`` positions,
    the directed edges between them, and each node's pinned coordinates.

    Nodes sit in id order and edges in the order ``build`` derived them — a
    component at a time in id order, each one's ``contains``/``consumes``/
    ``provides`` refs in authored order. The renderers walk both as given:
    that order, not any sorting of their own, is what makes the output
    deterministic.
    """

    nodes: tuple[Element, ...]
    edges: tuple[tuple[Ref, str, Ref], ...]
    positions: Mapping[Ref, Position]

    def render_svg(self, colouring: Colouring | None = None) -> str:
        """Hand-emitted SVG: boxes at the pinned coordinates, edges as lines
        with arrowheads, labels on both, the overlay (if any) as each box's
        fill with its class spelled on the box.

        Drawn edges-first so boxes cover the segments' ends, each segment
        clipped to the two boxes' borders so arrows touch boxes rather than
        vanish under them. Every number goes through ``_n`` and every order
        is the dataclass's own — that is the whole determinism story.
        """
        if self.nodes:
            xs = [position.x for position in self.positions.values()]
            ys = [position.y for position in self.positions.values()]
            left = min(xs) - _BOX_WIDTH / 2 - _MARGIN
            top = min(ys) - _BOX_HEIGHT / 2 - _MARGIN
            width = max(xs) - min(xs) + _BOX_WIDTH + 2 * _MARGIN
            height = max(ys) - min(ys) + _BOX_HEIGHT + 2 * _MARGIN
        else:  # a store with no diagram nodes is still a drawable picture
            left, top, width, height = 0.0, 0.0, 2 * _MARGIN, 2 * _MARGIN
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_n(left)} {_n(top)} {_n(width)} {_n(height)}">',
            f'<rect x="{_n(left)}" y="{_n(top)}" width="{_n(width)}" height="{_n(height)}" fill="{_SURFACE}"/>',
            "<defs>",
            '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"'
            ' markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="#52514e"/>',
            "</marker>",
            "</defs>",
        ]
        lines += self._svg_edges()
        lines += self._svg_boxes(colouring)
        lines.append("</svg>")
        return "\n".join(lines)

    def render_mermaid(self, colouring: Colouring | None = None) -> str:
        """The shared emitter's graph — the same node and edge spelling ``ab
        trace`` prints — plus, with an overlay, one ``classDef``/``class``
        pair per class. The class statements reuse the emitter's own node
        keys, which is why those keys are public: a private twin would be
        free to drift. Mermaid auto-lays-out; the pinned coordinates are
        SVG's to honour."""
        lines = [mermaid((element.id for element in self.nodes), self.edges)]
        if colouring is not None:
            classes = _classes(self.nodes, colouring)
            for caption, fill in classes.items():
                lines.append(f"  classDef {_class_name(caption)} fill:{fill},color:{_ink(fill)}")
            for caption in classes:
                members = ",".join(
                    node_key(element.id)
                    for element in self.nodes
                    if colouring.caption[element.id] == caption
                )
                lines.append(f"  class {members} {_class_name(caption)}")
        return "\n".join(lines)

    def render_d2(self, colouring: Colouring | None = None) -> str:
        """[d2](https://d2lang.com) source: one labelled box per node, one
        labelled arrow per edge, styles as flat key paths. Produced, never
        rendered — no d2 CLI or library is a dependency of this command."""
        lines = ["direction: right", ""]
        lines += [
            f'{node_key(element.id)}: "{_d2_text(element.title)}" {{\n  shape: rectangle\n}}'
            for element in self.nodes
        ]
        lines.append("")
        lines += [
            f"{node_key(source)} -> {node_key(target)}: {field}"
            for source, field, target in self.edges
        ]
        if colouring is not None:
            lines.append("")
            for element in self.nodes:
                key = node_key(element.id)
                fill = colouring.fill[element.id]
                lines.append(f'{key}.style.fill: "{fill}"')
                lines.append(f'{key}.style.font-color: "{_ink(fill)}"')
        return "\n".join(lines)

    def _svg_edges(self) -> list[str]:
        lines: list[str] = []
        for source, field, target in self.edges:
            ends = _border_points(self.positions[source], self.positions[target])
            if ends is None:
                # A self-edge has no direction to draw. The ref graph's own
                # cycles are `ab check`'s to report, not this renderer's.
                continue
            (x1, y1), (x2, y2) = ends
            lines.append(
                f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}"'
                f' stroke="{_FRAME}" stroke-width="0.06" marker-end="url(#arrow)"/>'
            )
            # The paint-order halo keeps the field label legible where it
            # sits on the line it names.
            lines.append(
                f'<text x="{_n((x1 + x2) / 2)}" y="{_n((y1 + y2) / 2 - 0.12)}"'
                f' text-anchor="middle" font-size="0.22" fill="{_FRAME}"'
                f' paint-order="stroke" stroke="{_SURFACE}" stroke-width="0.08">'
                f"{escape(field)}</text>"
            )
        return lines

    def _svg_boxes(self, colouring: Colouring | None) -> list[str]:
        lines: list[str] = []
        for element in self.nodes:
            position = self.positions[element.id]
            fill = colouring.fill[element.id] if colouring is not None else _SURFACE
            ink = _ink(fill)
            lines.append(
                f'<rect x="{_n(position.x - _BOX_WIDTH / 2)}" y="{_n(position.y - _BOX_HEIGHT / 2)}"'
                f' width="{_n(_BOX_WIDTH)}" height="{_n(_BOX_HEIGHT)}" rx="0.12"'
                f' data-ref="{escape(element.id, quote=True)}" fill="{fill}"'
                f' stroke="{_FRAME}" stroke-width="0.05"/>'
            )
            # Three lines when the overlay's class rides on the box, two
            # centred ones when it does not.
            caption = colouring.caption[element.id] if colouring is not None else None
            lines.append(
                f'<text x="{_n(position.x)}" y="{_n(position.y - 0.34 if caption else position.y - 0.12)}"'
                f' text-anchor="middle" font-size="0.32" font-weight="600" fill="{ink}"'
                f"{_fit(element.title, 0.32)}>{escape(element.title)}</text>"
            )
            lines.append(
                f'<text x="{_n(position.x)}" y="{_n(position.y + 0.02 if caption else position.y + 0.24)}"'
                f' text-anchor="middle" font-size="0.24" fill="{ink}"'
                f"{_fit(element.id, 0.24)}>{escape(element.id)}</text>"
            )
            if caption is not None:
                lines.append(
                    f'<text x="{_n(position.x)}" y="{_n(position.y + 0.38)}"'
                    f' text-anchor="middle" font-size="0.2" font-style="italic" fill="{ink}"'
                    f"{_fit(caption, 0.2)}>{escape(caption)}</text>"
                )
        return lines


def build(design: Design, root: Path, *, scope: str | None = None) -> Diagram:
    """Fold ``design`` and its pinned positions into the picture.

    Every in-scope diagram node must have a pinned position or this refuses
    with a ``LayoutError`` naming ``ab layout`` — the same verdict that
    command's own ``--check`` gives — because falling back to an auto-layout
    would quietly defeat the entire purpose of pinning positions. ``scope``
    keeps the subtree the site half keeps (reachability by refs outward), so
    one ``--scope`` flag means one thing across both halves of ``ab render``,
    and only in-scope nodes need pins.

    Raises ``UnknownRefError`` for a scope ref no element has, like ``show``,
    ``trace`` and the site's own scope do.
    """
    index = Index.from_design(design)
    if scope is not None and scope not in index.by_id:
        raise UnknownRefError(
            f"unknown --scope ref {scope!r}: no element in this store has that id"
        )
    reachable = subtree(index, scope) if scope is not None else None
    node_ids = {ref for ref in nodes(design) if reachable is None or ref in reachable}
    pinned = read_layout(root)
    positioned = {position.ref for position in pinned.positions}
    if lacking := sorted(node_ids - positioned):
        raise LayoutError(f"no pinned position for {', '.join(lacking)}; run ab layout to pin them")
    # dict.fromkeys over the triples: a ref repeated in one field draws once.
    # Both ends must be in scope — an edge whose source box is absent would
    # dangle out of the picture.
    edges = dict.fromkeys(
        (component.id, field, target)
        for component in sorted(design.components, key=lambda component: component.id)
        if component.id in node_ids
        for field, refs in (
            ("contains", component.contains),
            ("consumes", component.consumes),
            ("provides", component.provides),
        )
        for target in refs
        if target in node_ids
    )
    return Diagram(
        nodes=tuple(sorted((index.by_id[ref] for ref in node_ids), key=lambda e: e.id)),
        edges=tuple(edges),
        positions={
            position.ref: position for position in pinned.positions if position.ref in node_ids
        },
    )


# --- the overlays ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Colouring:
    """One overlay's answer per node: the fill to paint and the class to
    spell. Both travel together because a hue must never carry the meaning
    alone — the caption is the relief channel, drawn on the box in SVG and
    asserted on in the tests."""

    fill: Mapping[Ref, str]
    caption: Mapping[Ref, str]


def overlay_colours(overlay: str, design: Design, *, root: Path | None = None) -> Colouring:
    """The colouring ``overlay`` paints the diagram nodes with.

    ``state`` colours by ``Element.state``; ``milestone`` by membership in a
    milestone's ``scope`` — the flag carries no companion value, so the
    colouring answers "which milestone, if any" across all of them, ties
    going to the first milestone in id order; ``coverage`` by whether an
    element has an implementation-side reference (``implemented_by`` on a
    component, ``verified_by`` on a seam; externals are assumed, never
    implemented); ``churn`` by how many commits touched the element's
    ``source`` path.

    ``churn`` is the one overlay that leaves the design: it reads the git
    history of the repository the store lives in, which is why it alone
    takes ``root``. A store outside any repository has no history to read
    and every node lands in the zero bucket — a flat colouring, not a
    refusal, because "no history" is a fact about where the store lives,
    not a broken invocation.

    Raises ``ValueError`` for a name outside ``OVERLAYS``: a programming
    error, not a user-facing verdict (the CLI's own choice enum already
    refuses those before this is reached).
    """
    index = Index.from_design(design)
    node_ids = nodes(design)
    if overlay == "state":
        return Colouring(
            fill={ref: _STATE_FILL.get(index.by_id[ref].state, _NEUTRAL) for ref in node_ids},
            caption={ref: index.by_id[ref].state.value for ref in node_ids},
        )
    if overlay == "milestone":
        milestones = sorted(design.milestones, key=lambda milestone: milestone.id)
        # Slots in id order; beyond the palette's size the fill falls to the
        # neutral (slots are never cycled) while the caption keeps naming the
        # milestone, so an overflow member is never mistaken for a non-member.
        slot = {
            milestone.id: _CATEGORICAL[order]
            for order, milestone in enumerate(milestones)
            if order < len(_CATEGORICAL)
        }
        membership: dict[Ref, Ref] = {}
        for milestone in milestones:
            for ref in milestone.scope:
                membership.setdefault(ref, milestone.id)
        return Colouring(
            fill={ref: slot.get(membership.get(ref, ""), _NEUTRAL) for ref in node_ids},
            caption={ref: membership.get(ref, "in no milestone") for ref in node_ids},
        )
    if overlay == "coverage":

        def covered(element: Element) -> bool:
            if isinstance(element, Component):
                return bool(element.implemented_by)
            return isinstance(element, Seam) and bool(element.verified_by)

        return Colouring(
            fill={ref: _COVERED if covered(index.by_id[ref]) else _NEUTRAL for ref in node_ids},
            caption={
                ref: "covered" if covered(index.by_id[ref]) else "not covered" for ref in node_ids
            },
        )
    if overlay == "churn":
        counts = _commit_counts(root, index, node_ids)
        # The buckets an ordinal ramp of three can carry; the third absorbs
        # everything above it, which is all "changed a lot" ever needs to say.
        captions = ("0 changes", "1 change", "2+ changes")
        return Colouring(
            fill={ref: _ORDINAL[min(counts[ref], 2)] for ref in node_ids},
            caption={ref: captions[min(counts[ref], 2)] for ref in node_ids},
        )
    raise ValueError(f"no such overlay: {overlay!r}")


def _commit_counts(root: Path | None, index: Index, node_ids: tuple[Ref, ...]) -> Mapping[Ref, int]:
    """Commits per node source path, in the repository around ``root``."""
    if root is None:
        return dict.fromkeys(node_ids, 0)
    store = root.resolve()
    try:
        repo = repo_root(store)
    except GitError:
        return dict.fromkeys(node_ids, 0)
    return {
        ref: commit_count((store / index.by_id[ref].source).relative_to(repo), repo=repo)
        for ref in node_ids
    }


# --- the emitters' small parts ------------------------------------------------------


_BOX_WIDTH = 2.6
_BOX_HEIGHT = 1.4
"""Box size against ``ab layout``'s 4.0 spacing: wide enough for a title and
a ref, narrow enough that neighbours and edge labels never collide."""

_MARGIN = 1.0
"""Blank ring around the outermost boxes; labels of edge-end boxes live here."""


def _n(value: float) -> str:
    """One number, always the same spelling: two decimals, never an exponent
    — the fixed precision that keeps two runs byte-identical."""
    return f"{value:.2f}"


def _fit(text: str, font_size: float) -> str:
    """The SVG attribute that keeps a long label inside its box: ``textLength``
    squeezes the string to the box's inner width, applied only when the
    classic sans average (0.62 em per glyph) says it would spill.

    An estimate on purpose — measuring real glyph widths would mean a font
    dependency for a hand-emitted file — and a deterministic one, so the same
    label always gets the same squeeze."""
    if len(text) * font_size * 0.62 <= _BOX_WIDTH - 0.2:
        return ""
    return f' textLength="{_n(_BOX_WIDTH - 0.2)}" lengthAdjust="spacingAndGlyphs"'


def _ink(fill: str) -> str:
    """The text colour a fill can carry: whichever of the two primary inks
    contrasts more with it, by WCAG relative luminance. A pure function of
    the hex, so it cannot drift between runs or formats; light fills (luminance
    above ``0.179``) take the near-black ink, dark ones the white — ``0.179``
    is where the two inks' contrast ratios swap places."""
    red, green, blue = (int(fill[at : at + 2], 16) / 255 for at in (1, 3, 5))
    luminance = 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)
    return "#0b0b0b" if luminance > 0.179 else "#ffffff"


def _channel(value: float) -> float:
    """One sRGB channel linearized, the WCAG way."""
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _classes(elements: tuple[Element, ...], colouring: Colouring) -> dict[str, str]:
    """Caption to fill, in first-appearance order over the nodes — the order
    the classDef lines land in, and a deterministic one."""
    classes: dict[str, str] = {}
    for element in elements:
        classes.setdefault(colouring.caption[element.id], colouring.fill[element.id])
    return classes


def _class_name(caption: str) -> str:
    """A caption as a DSL-safe identifier: stable per caption, so the same
    colouring always spells the same class names."""
    return re.sub(r"[^0-9A-Za-z_]", "_", caption)


def _d2_text(title: str) -> str:
    """A title as d2 string content: quotes and backslashes escaped."""
    return title.replace("\\", "\\\\").replace('"', '\\"')


def _border_points(
    source: Position, target: Position
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Where a centre-to-centre line leaves one box and enters the other: the
    segment clipped to each rectangle's border, so arrows touch boxes rather
    than disappear under them. ``None`` for a self-edge, which has no
    direction to draw."""
    dx, dy = target.x - source.x, target.y - source.y
    if dx == 0 and dy == 0:
        return None
    reach = min(
        _BOX_WIDTH / 2 / abs(dx) if dx else math.inf,
        _BOX_HEIGHT / 2 / abs(dy) if dy else math.inf,
    )
    return (
        (source.x + dx * reach, source.y + dy * reach),
        (target.x - dx * reach, target.y - dy * reach),
    )
