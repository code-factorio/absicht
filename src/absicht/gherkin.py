"""Gherkin ``.feature`` rendering of a story's behavioural criteria.

One direction only: criteria in, Gherkin out, never parsed back. The output
is generated, never authored (``docs/spec/cli.md``'s features milestone), so
everything here is deterministic — the same story and criteria always render
the same bytes, which is what ``ab features --check`` diffs against and what
``ab packet --seal``'s ``scenarios_digest`` seals. Built once here so
``32-packet-cli.md``'s ``--features`` and ``33-features.md`` neither
reimplements Gherkin syntax.

This module takes a resolved story and its criteria. Which milestone's
criteria they are is the caller's walk (``Milestone.done_when`` and the
in-scope stories' acceptance), not this layer's knowledge. Criteria render in
the order given, which acceptance order already makes criterion-id order
(``#ac-1``, ``#ac-2``, …).
"""

from __future__ import annotations

import hashlib

from absicht.models import Criterion, CriterionKind, Story


def render_feature(story: Story, criteria: tuple[Criterion, ...]) -> str:
    """One ``.feature`` document for ``story``: a ``Feature:`` header whose
    description maps the story's own fields onto Gherkin's As a/I want/So
    that framing, then one ``Scenario:`` per behavioural criterion with
    ``Given``/``When``/``Then`` lines from the criterion's fields.

    Structural and measured criteria are skipped — they are ``ab verify``'s
    and the benchmark's concern (``docs/tasks/41-verify-rules.md``), not
    Gherkin's. A criterion with no ``given`` simply starts at ``When``, the
    way the model already lets a behavioural criterion omit it.
    """
    lines = [f"Feature: {story.title}"]
    lines += _narrative(story)
    for criterion in criteria:
        if criterion.kind is not CriterionKind.BEHAVIOURAL:
            continue
        lines += ["", f"  Scenario: {criterion.id}"]
        lines += _steps("Given", criterion.given)
        lines += [f"    When {criterion.when}"]
        lines += _steps("Then", criterion.then)
    return "\n".join(lines) + "\n"


def scenario_digest(features: dict[str, str]) -> str:
    """A stable hash over a set of rendered ``.feature`` files — what
    ``Packet.scenarios_digest`` stores and ``ab verify`` re-computes to catch
    scenario drift.

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


def _narrative(story: Story) -> list[str]:
    """The description block under the ``Feature:`` line: the classic user
    story as Gherkin narrative, one line per field the story actually
    carries — a story with no actor renders no ``As a`` line rather than an
    empty one. The title is the want; story titles read as imperatives
    ("Cancel an order"), and Gherkin wants the infinitive."""
    lines: list[str] = []
    if story.actor:
        lines.append(f"As a {story.actor}")
    lines.append(f"I want to {_lower_first(story.title)}")
    if story.outcome:
        lines.append(f"So that {story.outcome}")
    return ["", *(f"  {line}" for line in lines)]


def _steps(keyword: str, lines: tuple[str, ...]) -> list[str]:
    """A step section: the first line carries the keyword, the rest continue
    with ``And`` — Gherkin's spelling of a list inside one section."""
    if not lines:
        return []
    return [f"    {keyword} {lines[0]}", *(f"    And {line}" for line in lines[1:])]


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]
