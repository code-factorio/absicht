"""The vocabulary `ab check` and `ab verify` share: findings, and what they decide.

These tests pin the decisions `docs/tasks/04-findings.md` left open rather than
restating its field list: which of `--rule` and `--exclude-rule` wins when an id
is in both, that `info` never moves the exit code, and the minimal SARIF shape
code-scanning needs in order to annotate a diff.
"""

from __future__ import annotations

import pytest
from absicht.findings import (
    RULES,
    ExitCode,
    Finding,
    Report,
    Severity,
    finding,
)

from absicht.models import SCHEMA_VERSION


def _finding(
    rule_id: str,
    severity: Severity,
    *,
    ref: str | None = None,
    source: str | None = None,
) -> Finding:
    """A finding for the filter and render tests, where the catalog plays no part."""
    return Finding(
        rule_id=rule_id,
        severity=severity,
        message=f"{rule_id} fired",
        ref=ref,
        source=source,
        rule_explain=f"what {rule_id} checks",
    )


WARN_ONLY = Report(
    findings=(
        _finding("t/warn", Severity.WARN),
        _finding("t/info", Severity.INFO),
    )
)
WITH_ERROR = Report(
    findings=(
        _finding("t/error", Severity.ERROR),
        _finding("t/warn", Severity.WARN),
    )
)
MIXED = Report(
    findings=(
        _finding("a/error", Severity.ERROR, ref="component:x", source="components/x.md"),
        _finding("a/warn", Severity.WARN),
        _finding("b/info", Severity.INFO),
    )
)


# ------------------------------------------------------------------ exit codes


@pytest.mark.parametrize(
    ("report", "strict", "expected"),
    [
        (WITH_ERROR, False, ExitCode.FINDINGS),
        (WITH_ERROR, True, ExitCode.FINDINGS),
        (WARN_ONLY, False, ExitCode.OK),
        (WARN_ONLY, True, ExitCode.FINDINGS),
    ],
    ids=["error-no-strict", "error-strict", "warn-only-no-strict", "warn-only-strict"],
)
def test_exit_code_over_error_and_strict(report: Report, strict: bool, expected: ExitCode) -> None:
    assert report.exit_code(strict=strict) is expected


def test_info_alone_never_fails_the_run_even_under_strict() -> None:
    """`--strict` promotes warnings, not notes: info is advisory by definition."""
    report = Report(findings=(_finding("t/info", Severity.INFO),))

    assert report.exit_code(strict=True) is ExitCode.OK


def test_an_empty_report_exits_ok() -> None:
    assert Report().exit_code(strict=True) is ExitCode.OK


# -------------------------------------------------------------------- filtering


def test_rule_filter_keeps_only_the_named_rules() -> None:
    kept = MIXED.filtered(rules={"b/info"}, exclude=set(), min_severity=Severity.INFO)

    assert [f.rule_id for f in kept.findings] == ["b/info"]


def test_exclude_rule_drops_the_named_rules() -> None:
    kept = MIXED.filtered(rules=None, exclude={"a/error"}, min_severity=Severity.INFO)

    assert [f.rule_id for f in kept.findings] == ["a/warn", "b/info"]


def test_exclude_wins_when_an_id_is_both_included_and_excluded() -> None:
    """`--rule x --exclude-rule x` means x is out: the more specific ask wins."""
    kept = MIXED.filtered(rules={"a/error"}, exclude={"a/error"}, min_severity=Severity.INFO)

    assert kept.findings == ()


def test_min_severity_drops_everything_below_the_bar() -> None:
    kept = MIXED.filtered(rules=None, exclude=set(), min_severity=Severity.WARN)

    assert [f.rule_id for f in kept.findings] == ["a/error", "a/warn"]


def test_an_empty_rule_set_keeps_nothing() -> None:
    """`rules=None` is "no filter"; an empty set is honored as "filter to nothing"."""
    kept = MIXED.filtered(rules=set(), exclude=set(), min_severity=Severity.INFO)

    assert kept.findings == ()


def test_the_three_filters_compose() -> None:
    kept = MIXED.filtered(
        rules={"a/error", "b/info"},
        exclude={"b/info"},
        min_severity=Severity.WARN,
    )

    assert [f.rule_id for f in kept.findings] == ["a/error"]


# -------------------------------------------------------------------- rendering


def test_render_json_is_the_versioned_envelope_over_plain_findings() -> None:
    rendered = MIXED.render_json()

    assert rendered["schema_version"] == SCHEMA_VERSION
    assert rendered["findings"][0] == {
        "rule_id": "a/error",
        "severity": "error",
        "message": "a/error fired",
        "ref": "component:x",
        "source": "components/x.md",
        "rule_explain": "what a/error checks",
    }


def test_render_sarif_is_minimal_valid_sarif() -> None:
    report = Report(
        findings=(
            _finding("a/error", Severity.ERROR, ref="component:x", source="components/x.md"),
            _finding("b/warn", Severity.WARN),
            _finding("c/info", Severity.INFO),
        )
    )

    sarif = report.render_sarif()

    assert sarif["version"] == "2.1.0"
    (run,) = sarif["runs"]
    assert run["tool"]["driver"]["name"] == "absicht"
    results = run["results"]
    assert [r["level"] for r in results] == ["error", "warning", "note"]
    assert results[0]["ruleId"] == "a/error"
    assert results[0]["message"] == {"text": "a/error fired"}
    assert results[0]["locations"] == [
        {"physicalLocation": {"artifactLocation": {"uri": "components/x.md"}}}
    ]
    # A finding with no file has nowhere to annotate, so it carries no location.
    assert "locations" not in results[1]
    assert "locations" not in results[2]


def test_render_text_is_one_line_per_finding() -> None:
    report = Report(
        findings=(
            _finding("a/error", Severity.ERROR, source="components/x.md"),
            _finding("b/warn", Severity.WARN),
        )
    )

    assert report.render_text().splitlines() == [
        "error a/error: a/error fired (components/x.md)",
        "warn b/warn: b/warn fired",
    ]


# --------------------------------------------------------------------- catalog


def test_the_factory_attaches_the_catalog_explanation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(RULES, "t/registered", "what it checks, and why at this severity")

    made = finding("t/registered", severity=Severity.WARN, message="component:x has no owner")

    assert made.rule_explain == "what it checks, and why at this severity"


def test_the_factory_refuses_an_unregistered_rule() -> None:
    """A rule nobody can `--explain` must not be able to produce findings quietly."""
    with pytest.raises(KeyError):
        finding("t/never-registered", severity=Severity.WARN, message="component:x has no owner")
