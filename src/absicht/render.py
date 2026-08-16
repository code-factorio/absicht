"""Read-only projections of a resolved ``Design``, shared by every renderer.

Today that is one thing: the element view behind ``ab show REF`` — the element,
what points at it, what it points at — in the three spellings the command
offers. ``docs/tasks/26-render-site.md`` builds the site's element pages on
this same view ("literally reuse 21-show.md's function, don't re-derive it"),
which is why the view and its rendering live here rather than in
``absicht.cli``: the CLI sits at the top of the import stack, and the site
generator cannot import up.

Rendering is deterministic because the data under it is: neighbours keep the
order ``Index`` indexed them in, which is ``models.py``'s field declaration
order, so the same store always spells the same view.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from absicht.models import SCHEMA_VERSION, Design, Element
from absicht.resolve import Index, Reference


class UnknownRefError(Exception):
    """``REF`` names nothing in the store: a broken invocation, not a finding.

    ``ab show`` maps this to ``ExitCode.USAGE`` — the exit-code table's
    distinction between "the caller asked for something that is not there" and
    "the design has a problem".
    """


@dataclass(frozen=True, slots=True)
class Link:
    """One resolved edge of a neighbourhood: the element on the other side,
    and the field that carries the ref.

    The field belongs to the element nearer the focus — the focus itself for
    an outgoing hop, the pointing element for an incoming one — so a line like
    ``requirement:cancel-orders (realized_by)`` names both ends of the edge.
    """

    field: str
    other: Element


@dataclass(frozen=True, slots=True)
class Hop(Link):
    """An outgoing ``Link`` plus the hops it leads to, while depth remains."""

    deeper: tuple[Hop, ...] = ()


@dataclass(frozen=True, slots=True)
class Neighbourhood:
    """The answer to ``ab show``: one element with both sides of its graph."""

    element: Element
    outgoing: tuple[Hop, ...]
    incoming: tuple[Link, ...]

    def render_text(self, *, include_body: bool) -> str:
        lines = [f"{self.element.id} — {self.element.title}"]
        lines += [f"  {name}: {_value_text(value)}" for name, value in self._fields()]
        lines += _section(
            "points at:",
            (
                f"{'  ' * (level + 1)}{hop.other.id} ({hop.field})"
                for level, hop in _walk(self.outgoing)
            ),
        )
        lines += _section(
            "referenced by:", (f"  {link.other.id} ({link.field})" for link in self.incoming)
        )
        if include_body and self.element.body:
            lines += ["", self.element.body.rstrip()]
        return "\n".join(lines)

    def render_markdown(self, *, include_body: bool) -> str:
        """One Markdown document — the shape the site's element pages reuse."""
        lines = [f"# {self.element.title}", "", f"`{self.element.id}`"]
        lines += [f"- {name}: {_value_text(value)}" for name, value in self._fields()]
        lines += _section(
            "## Points at",
            (
                f"{'  ' * level}- `{hop.other.id}` — {hop.field}"
                for level, hop in _walk(self.outgoing)
            ),
        )
        lines += _section(
            "## Referenced by", (f"- `{link.other.id}` — {link.field}" for link in self.incoming)
        )
        if include_body and self.element.body:
            lines += ["", "## Body", "", self.element.body.rstrip()]
        return "\n".join(lines)

    def render_json(self, *, include_body: bool) -> dict[str, object]:
        """The ``--json``/``--format json`` envelope of ``00-conventions.md``."""
        exclude = None if include_body else {"body"}
        return {
            "schema_version": SCHEMA_VERSION,
            "element": self.element.model_dump(mode="json", exclude=exclude),
            "points_at": [_hop_json(hop) for hop in self.outgoing],
            "referenced_by": [
                {"field": link.field, "source": _fields_of(link.other)} for link in self.incoming
            ],
        }

    def _fields(self) -> tuple[tuple[str, Any], ...]:
        """The element's own fields for the prose renderers: declaration
        order, minus the header's four — `id` and `title` are the heading,
        `source` is provenance, `body` prints as its own block."""
        return tuple(
            (name, value)
            for name, value in self.element.model_dump(mode="json").items()
            if name not in ("id", "title", "source", "body") and value not in ("", None, [])
        )


def neighbourhood(design: Design, ref: str, *, depth: int) -> Neighbourhood:
    """Resolve ``ref`` into its neighbourhood, ``depth`` hops out.

    ``depth`` bounds the *outgoing* side only — "how far to follow refs" reads
    as following the element's own refs, while "what points at it" stays a
    neighbourhood view by stopping at one hop; expanding both directions would
    make ``show`` the pathfinder ``ab trace`` owns. ``depth 0`` therefore
    follows nothing out, leaving the element and whoever points at it. A ref
    whose target is not an element resolves to no neighbour on either side,
    the same policy ``Index.referenced_by`` already holds — reporting dangling
    refs is ``ab check``'s job, not a query's.
    """
    index = Index.from_design(design)
    element = index.by_id.get(ref)
    if element is None:
        raise UnknownRefError(f"unknown ref {ref!r}: no element in this store has that id")
    return Neighbourhood(
        element=element,
        # The first hop costs one unit of budget like every hop after it, so
        # the whole side is empty at depth 0 rather than quietly meaning 1.
        outgoing=(
            tuple(
                _hop(index, edge, remaining=depth - 1)
                for edge in index.references_from.get(ref, ())
                if edge.target in index.by_id
            )
            if depth > 0
            else ()
        ),
        incoming=tuple(
            Link(field=edge.field, other=index.by_id[edge.source])
            for edge in index.referenced_by.get(ref, ())
        ),
    )


def _hop(index: Index, edge: Reference, *, remaining: int) -> Hop:
    """One resolved outgoing edge, plus its own while budget remains.

    The budget is what makes cyclic graphs — a seam's provider provides that
    seam right back — safe: expansion stops when it runs out, not when the
    walk arrives somewhere it has already been. A view of a cyclic graph is a
    bounded tree, not a search.
    """
    deeper = (
        tuple(
            _hop(index, further, remaining=remaining - 1)
            for further in index.references_from.get(edge.target, ())
            if further.target in index.by_id
        )
        if remaining > 0
        else ()
    )
    return Hop(field=edge.field, other=index.by_id[edge.target], deeper=deeper)


def _walk(hops: tuple[Hop, ...], level: int = 0) -> Iterator[tuple[int, Hop]]:
    """Every hop with its distance from the focus, so the prose renderers
    indent by level without each re-implementing the recursion."""
    for hop in hops:
        yield level, hop
        yield from _walk(hop.deeper, level + 1)


def _section(heading: str, entries: Iterator[str]) -> list[str]:
    """A headed block, omitted whole when it has no entries — a view with
    nothing on one side says nothing about that side rather than proving an
    empty heading at the reader."""
    rows = list(entries)
    return ["", heading, *rows] if rows else []


def _value_text(value: Any) -> str:
    """One line per field value: strings as themselves, lists of strings
    comma-joined, anything structured (fields, criteria, units) as compact
    JSON rather than a bespoke pretty-printer per shape."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ", ".join(value)
    return json.dumps(value)


def _fields_of(element: Element) -> dict[str, object]:
    """A neighbour's fields: everything but its prose and provenance. The body
    is the focus element's to print (under ``--body``), and where a neighbour
    lives is not this view's story."""
    return element.model_dump(mode="json", exclude={"body", "source"})


def _hop_json(hop: Hop) -> dict[str, object]:
    return {
        "field": hop.field,
        "target": _fields_of(hop.other),
        "deeper": [_hop_json(deeper) for deeper in hop.deeper],
    }
