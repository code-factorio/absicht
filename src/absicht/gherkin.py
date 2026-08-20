"""Gherkin ``.feature`` rendering of a behavior and its observations.

One direction only: behaviors in, Gherkin out, never parsed back. The output
is generated, never authored, so everything here is deterministic — the same
behavior always renders the same bytes, which is what ``ab features --check``
diffs against and what ``ab packet --seal``'s digest seals.

The mapping is the model's own shape, not a translation: a behavior's
``trigger`` is what happened, so it is the ``When``; an observation is one
expectation about the result, so it is a ``Then`` and gets a scenario of its
own. Each scenario is named by the observation's id, which is the id a step
definition binds to and the id that survives every rewording.

``outcome`` and the effective ``timing`` ride as tags, because they change
what a runner does with a scenario and a tag is the one thing a runner can
filter on. A ``must_not`` carries no timing tag: it means at no point.

Which behaviors are rendered is the caller's walk (a milestone's ``satisfy``,
or the whole design), not this layer's knowledge.
"""

from __future__ import annotations

import hashlib

from absicht.models.design import Behavior, Observation
from absicht.resolve import Index, effective_timing


def render_feature(behavior: Behavior, index: Index) -> str:
    """One ``.feature`` document for ``behavior``.

    A ``Feature:`` header whose description is the trigger, then one
    ``Scenario:`` per observation, in the order the behavior states them —
    which is observation-id order (``#obs-1``, ``#obs-2``, …) in any file
    somebody has not shuffled.
    """
    lines = [f"Feature: {behavior.title}", "", f"  {behavior.trigger}"]
    for observation in behavior.observations:
        lines += ["", f"  {_tags(observation, index)}", f"  Scenario: {observation.id}"]
        lines += [f"    # at {observation.at}"]
        lines += [f"    When {behavior.trigger}"]
        lines += [f"    Then {observation.statement}"]
    return "\n".join(lines) + "\n"


def observations_digest(features: dict[str, str]) -> str:
    """A stable hash over a set of rendered ``.feature`` files — what
    ``PacketLock.observations_digest`` stores and ``ab verify`` re-computes to
    catch drift between what was handed over and what is being verified.

    Files fold in sorted-by-filename order, so dict insertion order cannot
    move the digest. Each file's *name* is hashed with its content — a rename
    counts as a change even when the bytes are identical, because the step
    definitions' home moved.
    """
    digest = hashlib.sha256()
    for name, content in sorted(features.items()):
        # The NUL separators keep name and content boundaries unambiguous in
        # the hash input; neither can legitimately contain one.
        digest.update(f"{name}\0{content}\0".encode())
    return digest.hexdigest()


def _tags(observation: Observation, index: Index) -> str:
    """The scenario's tags: what the outcome demands, and when it holds.

    A runner filters on these — ``@should`` never fails a build, ``@eventual``
    needs a wait — so they are tags rather than prose nobody can select on.
    """
    tags = [f"@{observation.outcome.value}"]
    if (timing := effective_timing(observation, index)) is not None:
        tags.append(f"@{timing.value}")
    return " ".join(tags)
