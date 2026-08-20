"""Where the diagram draws each box.

Not part of the design: a position says nothing about the system. It lives
beside one because a diagram is only worth building spatial memory on when
the same element sits in the same place on every build, and that is a fact
somebody has to pin.
"""

from __future__ import annotations

from absicht.models.design import Record, Ref


class Position(Record):
    """One diagram node's pinned coordinates."""

    ref: Ref
    x: float
    y: float


class Layout(Record):
    """The `layout.yaml` singleton: one pinned position per diagram node.

    A tuple in id order, like every collection in the design: the dump's
    order is the model's own, so byte-identical output does not rest on
    dict insertion order.
    """

    positions: tuple[Position, ...] = ()
