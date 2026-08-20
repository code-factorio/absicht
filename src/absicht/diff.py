"""What changed in the design between two revisions, as elements rather than lines.

``ab diff REF_A REF_B`` builds the ``Design`` at each revision through
``absicht.build``'s in-memory path (no artifact is written for either side)
and compares them element by element: decisions added, interfaces whose
contract moved, requirements dropped, state transitions. A diff entry is a
change, not a problem — it borrows findings' "structured result, rendered per
``--format``" shape, not its vocabulary: nothing here is a severity and the
command never exits non-zero for having found changes.

The comparison is the straightforward one the spec asks for: elements
present in both revisions are compared by id, field by field, over
``model_dump()``. ``state`` is carved out into its own change shape because
the spec names state transitions as a thing worth reading on their own; the
id needs no comparison (it is the join key) and ``kind`` is derived from it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from absicht.build import build
from absicht.models.design import FORMAT_VERSION, Element, State
from absicht.render import UnknownRefError
from absicht.resolve import Index, subtree


@dataclass(frozen=True, slots=True)
class Added:
    """An element that exists at REF_B and did not at REF_A."""

    kind: str
    ref: str


@dataclass(frozen=True, slots=True)
class Removed:
    """An element that existed at REF_A and does not at REF_B."""

    kind: str
    ref: str


@dataclass(frozen=True, slots=True)
class StateChanged:
    """An element present in both revisions whose ``state`` moved.

    Not a ``FieldChanged``: the spec calls state transitions out by name, and
    a changelog that has to grep for ``field: state`` to find them has lost
    the distinction it exists to carry.
    """

    ref: str
    before: State
    after: State


@dataclass(frozen=True, slots=True)
class FieldChanged:
    """An element present in both revisions with a field that moved.

    ``before``/``after`` are the field's ``model_dump(mode="json")`` values —
    JSON primitives, so both renderers spell a date or a ref list the same
    way the artifact does.
    """

    ref: str
    field: str
    before: object
    after: object


Change = Added | Removed | StateChanged | FieldChanged
"""Every shape a diff entry takes; the renderers dispatch over this union."""


def diff(
    store: Path,
    ref_a: str,
    ref_b: str,
    *,
    scope: str | None = None,
    kind: str | None = None,
) -> DesignDiff:
    """Compare the store's design at two revisions.

    ``--scope`` restricts the compared elements to a subtree, selected the
    way ``ab render --scope`` selects one — which side's edges to walk is not
    a choice this gets to make quietly, so both sides' subtrees are unioned:
    an element the subtree lost between the revisions is exactly a change to
    report, not one scoping should hide. Raises ``UnknownRefError`` for a
    scope ref neither revision knows.

    Build's own failures pass through for the CLI to map: a revision that
    does not resolve is ``GitError``, a store that does not load cleanly at
    either revision is ``BuildError``.
    """
    before_index = Index(build(store, rev=ref_a))
    after_index = Index(build(store, rev=ref_b))
    scope_set: frozenset[str] | None = None
    if scope is not None:
        if scope not in before_index.local and scope not in after_index.local:
            raise UnknownRefError(
                f"unknown --scope ref {scope!r}: no element in this store has that id"
            )
        scope_set = subtree(before_index, scope) | subtree(after_index, scope)
    before_by_id = _selected(before_index, kind=kind, scope_set=scope_set)
    after_by_id = _selected(after_index, kind=kind, scope_set=scope_set)

    changes: list[Change] = [
        Added(kind=ref.split(":", 1)[0], ref=ref)
        for ref in sorted(set(after_by_id) - set(before_by_id))
    ]
    changes.extend(
        Removed(kind=ref.split(":", 1)[0], ref=ref)
        for ref in sorted(set(before_by_id) - set(after_by_id))
    )
    for ref in sorted(before_by_id.keys() & after_by_id.keys()):
        # Same id means same kind prefix means the same model, so the two
        # dumps hold the same fields; `state` is compared first so a
        # transition reads before the field changes on the same element.
        before = before_by_id[ref].model_dump(mode="json")
        after = after_by_id[ref].model_dump(mode="json")
        if before["state"] != after["state"]:
            changes.append(StateChanged(ref, State(before["state"]), State(after["state"])))
        changes.extend(
            FieldChanged(ref, field, before[field], after[field])
            for field in sorted(before.keys() - {"state"})
            if before[field] != after[field]
        )
    return DesignDiff(ref_a=ref_a, ref_b=ref_b, changes=tuple(changes))


def _selected(
    index: Index, *, kind: str | None, scope_set: frozenset[str] | None
) -> dict[str, Element]:
    """The index's elements narrowed by ``--kind`` and ``--scope``, keyed by id.

    A plain id-prefix test for the kind, like every ``Kind``-filtered command
    below the CLI: the prefix is part of what a `Ref` is, so no lookup is
    needed to know an element's kind.
    """
    return {
        ref: element
        for ref, element in index.local.items()
        if (kind is None or ref.startswith(f"{kind}:")) and (scope_set is None or ref in scope_set)
    }


@dataclass(frozen=True, slots=True)
class DesignDiff:
    """The element-level changes between two revisions, in renderable order."""

    ref_a: str
    ref_b: str
    changes: tuple[Change, ...]

    def render_text(self) -> str:
        """One line per change with the changelog glyphs a terminal already
        reads: ``+`` added, ``-`` removed, ``~`` changed, the field named
        between the two values."""
        return "\n".join(_line(change) for change in self.changes)

    def render_json(self) -> dict[str, object]:
        """The ``--format json`` envelope from docs/tasks/00-conventions.md."""
        return {
            "format_version": FORMAT_VERSION,
            "from": self.ref_a,
            "to": self.ref_b,
            "changes": [_change_json(change) for change in self.changes],
        }

    def render_markdown(self) -> str:
        """A changelog-shaped document: one section per change shape, in the
        spec's own framing — additions, state transitions — plus the other
        two a diff can hold. Empty sections are omitted rather than announced;
        an empty diff is the empty document."""
        sections = []
        if added := [c for c in self.changes if isinstance(c, Added)]:
            sections.append(("## Added", [f"- `{c.ref}`" for c in added]))
        if removed := [c for c in self.changes if isinstance(c, Removed)]:
            sections.append(("## Removed", [f"- `{c.ref}`" for c in removed]))
        if states := [c for c in self.changes if isinstance(c, StateChanged)]:
            sections.append(
                ("## State transitions", [f"- `{c.ref}`: {c.before} -> {c.after}" for c in states])
            )
        if fields := [c for c in self.changes if isinstance(c, FieldChanged)]:
            sections.append(
                (
                    "## Changed",
                    [
                        f"- `{c.ref}` — {c.field}: {_text(c.before)} -> {_text(c.after)}"
                        for c in fields
                    ],
                )
            )
        return "\n\n".join(f"{heading}\n\n" + "\n".join(bullets) for heading, bullets in sections)


def _line(change: Change) -> str:
    match change:
        case Added(ref=ref):
            return f"+ {ref}"
        case Removed(ref=ref):
            return f"- {ref}"
        case StateChanged(ref=ref, before=before, after=after):
            return f"~ {ref} state: {before} -> {after}"
        case FieldChanged(ref=ref, field=field, before=before, after=after):
            return f"~ {ref} {field}: {_text(before)} -> {_text(after)}"
        case _:
            assert_never(change)


def _change_json(change: Change) -> dict[str, object]:
    match change:
        case Added(kind=kind, ref=ref):
            return {"type": "added", "kind": kind, "ref": ref}
        case Removed(kind=kind, ref=ref):
            return {"type": "removed", "kind": kind, "ref": ref}
        case StateChanged(ref=ref, before=before, after=after):
            return {"type": "state", "ref": ref, "before": before, "after": after}
        case FieldChanged(ref=ref, field=field, before=before, after=after):
            return {"type": "field", "ref": ref, "field": field, "before": before, "after": after}
        case _:
            assert_never(change)


def _text(value: object) -> str:
    """A field value for the text and markdown lines: a plain string goes out
    unquoted, everything else takes its JSON spelling — the one a list, a
    date or a null already has in the artifact."""
    return value if isinstance(value, str) else json.dumps(value)
