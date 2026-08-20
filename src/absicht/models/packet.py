"""What an agent is handed: bounded, self-contained, and offline-readable.

A packet is not the design. It is one slice of it, chosen by a milestone, and
the choosing is the whole value: an agent given everything reads nothing, and
an agent given only its own scope invents the rest.

It says what must become true, what must stay true, and where the reader is
free. It never says how the work is done or in what order, and what a consumer
does with it is not defined here.

Two fidelities, because there are two kinds of thing in a slice. What the
agent may change arrives whole. What it must not change arrives as a contract
— the surface, and nothing behind it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from absicht.models.design import FORMAT_VERSION, ObservationId, Record, Ref


class Fidelity(StrEnum):
    FULL = "full"  # in scope: every field
    CONTRACT = "contract"  # one ring out: the surface, nothing behind it


class PacketElement(Record):
    ref: Ref
    fidelity: Fidelity
    element: dict[str, object]
    """The element as built. A dict, not a typed record: a packet is read by
    things that are not this Python, and a shape stripped to its contract is
    no longer the model's shape."""


class Packet(Record):
    """The brief for one milestone."""

    format_version: int = FORMAT_VERSION
    milestone: Ref
    design: Ref
    design_rev: str = ""
    """The store commit it was assembled from, so a verification can run
    offline against the same design."""
    outcome: str = ""

    elements: tuple[PacketElement, ...] = ()

    satisfy: tuple[Ref, ...] = ()
    """The behaviors this slice must newly satisfy. The new work."""
    must_not_break: tuple[Ref, ...] = ()
    """Active behaviors whose observations touch the scope. Standing
    expectations, not new work: breaking one is a regression, and this is the
    mechanical form of "do not regress the rest of the system"."""
    must_hold: tuple[Ref, ...] = ()
    may_decide: tuple[str, ...] = ()
    """Where the agent is free. Without it, an agent asks about everything or
    invents everything."""
    unresolved: tuple[Ref, ...] = ()
    rejections: tuple[Ref, ...] = ()  # do not propose these again
    done_when: tuple[ObservationId, ...] = ()


class PacketLock(Record):
    """What a sealed packet was sealed against.

    Written beside the packet and read back by `verify`, so a verification
    runs in CI with no design store: the commit and the digest are everything
    "handed over against this" means. Both ends go through this record, so the
    writer's and the reader's spelling cannot drift.
    """

    format_version: int = FORMAT_VERSION
    design_rev: str = Field(min_length=1)
    observations_digest: str = Field(min_length=1)
