"""A repository's `.absicht` file: where the design lives, and how far it got.

The marker is a hint dropped in an implementing repository so an agent that
starts from the code can find the design. It is never authority: the store
says which component is implemented where, and `ab marker sync` writes that
here. What the marker adds is the watermark — the last milestone whose work
landed in this repository — because nothing in the store can know it.

A watermark tends to over-claim: a merge stamps it whether or not the work
was finished. It is evidence, not proof, and `ab verify` is what turns one
into the other.
"""

from __future__ import annotations

from absicht.models.design import Record, Ref


class Watermark(Record):
    """How far one component's code in this repository has come."""

    id: Ref
    """The component. `Design.repositories` says which repository this is."""
    path: str = "."
    """Where inside the repository, matching the component's `implemented_by`."""
    at: Ref | None = None
    """The last milestone landed here."""
    design_rev: str | None = None
    """The design store's head when it landed."""


class Marker(Record):
    """The `.absicht` file itself."""

    design: str
    """Path or URL of the store. Spelled by whoever wrote the marker."""
    units: tuple[Watermark, ...] = ()
