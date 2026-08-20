"""One vocabulary for "something is wrong", shared by ``ab check`` and ``ab verify``.

This module represents, filters and renders findings; it never produces them.
The rules that decide what is wrong live in ``absicht.check`` and
``absicht.verify``, each registering its ids in ``RULES`` at import time so
``ab check --explain ID`` — the only command with that flag, per
``docs/spec/cli.md`` — has one home to print from. ``absicht.packet``
registers its one rule-shaped failure there the same way: assembly can hit a
real problem with the design (a milestone with no scope) and represents it in
this vocabulary rather than a third one, even though ``ab packet`` exposes no
``--rule``. ``absicht.markers`` registers its three marker-disagreement rules
there for the same reason — ``ab marker check`` reports in this vocabulary
but has no ``--rule`` of its own.

``Severity`` and ``ExitCode`` are defined here rather than in
``absicht.cli._common``, where they started: the CLI sits at the top of the
import-linter stack and this module near the bottom, so the two value-only
enums both sides share moved down to the one layer each may import.
``_common`` still imports ``ExitCode`` for the surface's own use.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import Field

from absicht.models.design import FORMAT_VERSION, Record


class ExitCode(IntEnum):
    """What the shell sees.

    ``FINDINGS`` versus ``USAGE`` is the distinction that matters: CI treats the
    first as a real result about the design and the second as a broken pipeline.
    ``USAGE`` is also what Click exits with on a bad flag, so the two agree
    without us having to intercept anything.
    """

    OK = 0
    """Success, or advisory findings only."""
    FINDINGS = 1
    """Findings at error severity — validation, verification, drift."""
    USAGE = 2
    """Usage error: bad flags, unknown ref, no store."""
    INTERNAL = 3
    """Internal error."""
    SCHEMA_MISMATCH = 4
    """Format version mismatch; run ``ab migrate``."""


class Severity(StrEnum):
    """The grade of a finding: the values ``--severity`` chooses from."""

    ERROR = "error"
    WARN = "warn"
    INFO = "info"

    @property
    def rank(self) -> int:
        """INFO < WARN < ERROR, so a severity minimum is a rank comparison.

        Alphabetical order on the values is wrong ("error" sorts first), which
        is why the order is spelled out instead of derived.
        """
        return {Severity.INFO: 0, Severity.WARN: 1, Severity.ERROR: 2}[self]


class Finding(Record):
    """One thing wrong with a design or a diff, in the shape every renderer reads."""

    rule_id: str = Field(min_length=1)
    severity: Severity
    message: str = Field(min_length=1)
    ref: str | None = None
    """The element the finding is about, when there is one."""
    source: str | None = None
    """File path within the store, from the element's provenance."""
    rule_explain: str
    """What ``--explain`` prints for the rule. Build through ``finding()``."""


RULES: dict[str, str] = {}
"""Every rule id a rule-producing module can emit, with its explanation.

Rule modules add theirs at import time (``RULES["policy/x"] = "..."``). A plain
dict, deliberately not a registry class: a dozen rules do not need a plugin
system, and ``--explain`` is a lookup, not a discovery.
"""


def finding(
    rule_id: str,
    *,
    severity: Severity,
    message: str,
    ref: str | None = None,
    source: str | None = None,
) -> Finding:
    """Build a finding, pulling its ``--explain`` text from the catalog.

    The construction path rules should use: it makes a rule nobody registered a
    loud ``KeyError`` at the finding's birth rather than a silent gap in
    ``--explain`` later.
    """
    return Finding(
        rule_id=rule_id,
        severity=severity,
        message=message,
        ref=ref,
        source=source,
        rule_explain=RULES[rule_id],
    )


_SARIF_LEVEL: dict[Severity, str] = {
    Severity.ERROR: "error",
    Severity.WARN: "warning",
    Severity.INFO: "note",
}
"""SARIF 2.1.0 spells its middle and bottom levels differently than we do."""


class Report(Record):
    """The graded result of a check run: filter it, exit on it, render it."""

    findings: tuple[Finding, ...] = ()

    def filtered(
        self,
        *,
        rules: set[str] | None,
        exclude: set[str],
        min_severity: Severity,
    ) -> Report:
        """Apply ``--rule``, ``--exclude-rule`` and ``--severity`` in one pass.

        An id that is both included and excluded is excluded — the more
        specific ask wins. ``rules=None`` means no include filter; an empty set
        is honored as "keep nothing", which is what an explicit empty ``--rule``
        asks for.
        """
        kept = tuple(
            f
            for f in self.findings
            if (rules is None or f.rule_id in rules)
            and f.rule_id not in exclude
            and f.severity.rank >= min_severity.rank
        )
        return Report(findings=kept)

    def exit_code(self, *, strict: bool) -> ExitCode:
        """``FINDINGS`` on any ``error``, or on any ``warn`` under ``--strict``; else ``OK``.

        ``info`` never moves the exit: it is advisory by definition, and
        ``--strict`` promotes warnings, not notes.
        """
        grades = {f.severity for f in self.findings}
        if Severity.ERROR in grades or (strict and Severity.WARN in grades):
            return ExitCode.FINDINGS
        return ExitCode.OK

    def render_text(self) -> str:
        """One line per finding: ``severity rule-id: message``, plus the file when known.

        The element a finding is about is named in the message (the rules write
        it that way) and carried structurally by ``ref``; the text line adds
        only what a human fixing the store needs next: where to look.
        """
        lines = []
        for f in self.findings:
            line = f"{f.severity} {f.rule_id}: {f.message}"
            if f.source:
                line += f" ({f.source})"
            lines.append(line)
        return "\n".join(lines)

    def render_json(self) -> dict[str, object]:
        """The ``--json``/``--format json`` envelope from ``docs/tasks/00-conventions.md``."""
        return {
            "format_version": FORMAT_VERSION,
            "findings": [f.model_dump(mode="json") for f in self.findings],
        }

    def render_sarif(self) -> dict[str, object]:
        """Minimal SARIF 2.1.0: enough for code-scanning to annotate a diff, no more.

        A finding with no ``source`` gets no location — an annotation needs
        somewhere to land, and a system-wide finding has none.
        """
        results: list[dict[str, object]] = []
        for f in self.findings:
            result: dict[str, object] = {
                "ruleId": f.rule_id,
                "level": _SARIF_LEVEL[f.severity],
                "message": {"text": f.message},
            }
            if f.source is not None:
                result["locations"] = [
                    {"physicalLocation": {"artifactLocation": {"uri": f.source}}}
                ]
            results.append(result)
        return {
            "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "absicht"}}, "results": results}],
        }
