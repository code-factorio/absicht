"""``ab check``: the three finding layers wired into a command.

The layers themselves are pinned in ``tests/test_check.py`` against the same
fixtures; what this module pins is everything task 15 owned — the exit code,
the bytes on stdout, and the flags that shape them:

- the fixtures' end-to-end verdicts: ``clean`` and ``composite`` are empty at
  every severity, ``broken`` always exits ``FINDINGS``, and ``brownfield`` —
  which carries one error next to its warning — needs ``--exclude-rule`` to
  show the warnings-only → ``OK`` / ``--strict`` → ``FINDINGS`` half of the
  task's line: the fixture, not the task text, is the truth of what it holds;
- ``--rule`` / ``--exclude-rule`` / ``--severity`` change the report and,
  where they cross the error threshold, the exit code;
- ``--format json`` / ``--format sarif`` reach their renderers rather than
  ``render_text()``, and ``--json`` folds into a default ``--format`` without
  overriding an explicit one (docs/adr/0001);
- ``--changed-only`` against a throwaway repo in the shape of
  ``tests/test_git.py``'s fixture;
- ``--explain``, which answers from the rule catalog without reading a store;
- the model addendum's severity contract on top of both: each new error rule
  alone exits ``FINDINGS``, its one warning alone exits ``OK`` until
  ``--strict`` promotes it, and ``--explain`` answers for every id the pinned
  table names — the handled-upstream ids included.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.findings import RULES, Severity
from absicht.models import SCHEMA_VERSION

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "systems"

BROKEN_RULES = {
    "schema/yaml-syntax",
    "schema/validation",
    "integrity/dangling-ref",
    "integrity/cycle",
    "integrity/seam-references-resource",
    "integrity/observation-at-wrong-kind",
    "integrity/composition-cycle",
    "integrity/supersession-cycle",
    "policy/unknown-needs-owner",
    "policy/one-way-needs-rationale",
    "policy/external-assumptions-expired",
    "policy/behavior-needs-observations",
    "policy/requirement-needs-behavior",
    "policy/superseded-in-must-satisfy",
}
"""Everything `broken/` was built to trip, across all three layers — the
combination itself is under test as much as any one finding. The addendum's
three handled-upstream ids are deliberately absent: they surface as
`schema/validation` (the `must_not` timing) and `integrity/dangling-ref` (the
unresolvable `at` and `supersedes`), never under their own ids."""

ADDENDUM_RULES = (
    "integrity/seam-references-resource",
    "integrity/observation-at-unresolvable",
    "integrity/observation-at-wrong-kind",
    "integrity/composition-cycle",
    "integrity/supersedes-unresolvable",
    "integrity/supersession-cycle",
    "integrity/note-promoted-to-unresolvable",
    "schema/must-not-has-timing",
    "policy/behavior-needs-observations",
    "policy/requirement-needs-behavior",
    "policy/superseded-in-must-satisfy",
)
"""The addendum's whole rule table, as pinned in
`docs/tasks/50-addendum-conventions.md` — the three enforced upstream
included, whose registration is the point: `--explain` must answer for every
id the addendum implies, emitted or not."""


def _rule_ids(stdout: str) -> set[str]:
    """The rule ids of a text report, whose finding lines read
    `severity rule-id: message`.

    Only severity-prefixed lines are finding lines: a message can itself span
    lines (a YAML parse error carries pyyaml's context lines), and those
    continuations are not findings.
    """
    grades = {grade.value for grade in Severity}
    return {
        tokens[1].rstrip(":")
        for line in stdout.splitlines()
        if (tokens := line.split(maxsplit=2)) and tokens[0] in grades
    }


# --- the fixtures' verdicts ---------------------------------------------------


@pytest.mark.parametrize("name", ["clean", "composite"])
@pytest.mark.parametrize(
    "argv", [[], ["--severity", "error"], ["--severity", "warn"], ["--severity", "info"]]
)
def test_a_store_with_nothing_wrong_is_empty_and_ok_at_every_severity(
    name: str, argv: list[str]
) -> None:
    result = runner.invoke(app, ["--store", str(FIXTURES / name), "check", *argv])

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""


@pytest.mark.parametrize("argv", [[], ["--severity", "info"], ["--strict"]])
def test_broken_exits_findings_whatever_the_severity_or_strictness(argv: list[str]) -> None:
    """Fourteen of `broken/`'s sixteen findings are errors, so no flag
    combination can argue them below the threshold — which is the point of the
    fixture."""
    result = runner.invoke(app, ["--store", str(FIXTURES / "broken"), "check", *argv])

    assert result.exit_code == ExitCode.FINDINGS


def test_broken_combines_all_three_layers_into_one_report() -> None:
    result = runner.invoke(app, ["--store", str(FIXTURES / "broken"), "check"])

    assert result.exit_code == ExitCode.FINDINGS
    assert _rule_ids(result.stdout) == BROKEN_RULES


def test_brownfield_exits_findings_because_its_unknown_requirement_is_an_error() -> None:
    """The task text calls `brownfield/` "warnings only", but the fixture its
    own siblings built holds `requirement:audit-trail` unknown and unowned —
    an error by the policy layer's own severity contract, so `OK` at default
    severity was never this store's verdict. The expired external the gaps
    task added and the addendum's no-active-behavior warning are two more
    warnings beside it, not a second error."""
    result = runner.invoke(app, ["--store", str(FIXTURES / "brownfield"), "check"])

    assert result.exit_code == ExitCode.FINDINGS
    assert _rule_ids(result.stdout) == {
        "policy/unknown-needs-owner",
        "policy/requirement-needs-realizer",
        "policy/external-assumptions-expired",
        "policy/requirement-needs-behavior",
    }


def test_a_warnings_only_report_passes_until_strict_promotes_it() -> None:
    """The other half of the task's brownfield line, on the half of the store
    that is warnings: with the error rule excluded the report is advisory
    only — `OK` — until `--strict` promotes the warning, exactly the
    distinction CI reads off the exit code."""
    argv = [
        "--store",
        str(FIXTURES / "brownfield"),
        "check",
        "--exclude-rule",
        "policy/unknown-needs-owner",
    ]

    plain = runner.invoke(app, argv)
    strict = runner.invoke(app, [*argv, "--strict"])

    assert plain.exit_code == ExitCode.OK
    assert "warn policy/requirement-needs-realizer" in plain.stdout
    assert strict.exit_code == ExitCode.FINDINGS


# --- the report-shaping flags -------------------------------------------------


def test_rule_limits_the_report_and_the_error_threshold_with_it() -> None:
    """`--rule` keeps one rule's findings and nothing else: the expired
    external alone is advisory (`OK`), the unowned unknown alone crosses the
    threshold (`FINDINGS`) — the same flag moves both dials."""
    expired = runner.invoke(
        app,
        [
            "--store",
            str(FIXTURES / "broken"),
            "check",
            "--rule",
            "policy/external-assumptions-expired",
        ],
    )
    unowned = runner.invoke(
        app, ["--store", str(FIXTURES / "broken"), "check", "-r", "policy/unknown-needs-owner"]
    )

    assert expired.exit_code == ExitCode.OK
    assert _rule_ids(expired.stdout) == {"policy/external-assumptions-expired"}
    assert unowned.exit_code == ExitCode.FINDINGS
    assert _rule_ids(unowned.stdout) == {"policy/unknown-needs-owner"}


def test_severity_error_drops_the_advisory_findings_from_the_report() -> None:
    """`--severity error` keeps the fourteen errors and drops the fixture's two
    warnings — the expired external and the addendum's no-active-behavior —
    without changing the verdict, because an error crosses the threshold on
    its own."""

    result = runner.invoke(
        app, ["--store", str(FIXTURES / "broken"), "check", "--severity", "error"]
    )

    assert result.exit_code == ExitCode.FINDINGS
    assert _rule_ids(result.stdout) == BROKEN_RULES - {
        "policy/external-assumptions-expired",
        "policy/requirement-needs-behavior",
    }


# --- the addendum's severity and exit-code contract ----------------------------


@pytest.mark.parametrize(
    "rule_id",
    [
        "integrity/seam-references-resource",
        "integrity/observation-at-wrong-kind",
        "integrity/composition-cycle",
        "integrity/supersession-cycle",
        "policy/behavior-needs-observations",
        "policy/superseded-in-must-satisfy",
    ],
)
def test_each_addendum_error_rule_alone_exits_findings(rule_id: str) -> None:
    """`--rule` isolates one addendum error on `broken/`'s clearly-named file:
    alone, it still crosses the threshold — `FINDINGS` is what CI reads, and
    an error that could be argued below it is a warning mislabeled."""

    result = runner.invoke(app, ["--store", str(FIXTURES / "broken"), "check", "--rule", rule_id])

    assert result.exit_code == ExitCode.FINDINGS
    assert _rule_ids(result.stdout) == {rule_id}


def test_the_addendum_warning_alone_passes_until_strict_promotes_it() -> None:
    """The addendum's one warning, alone: advisory by default (`OK`) and
    promoted by `--strict` (`FINDINGS`) — the same distinction the
    pre-addendum warning rules keep, so CI can adopt it without new rules."""

    argv = [
        "--store",
        str(FIXTURES / "broken"),
        "check",
        "--rule",
        "policy/requirement-needs-behavior",
    ]

    plain = runner.invoke(app, argv)
    strict = runner.invoke(app, [*argv, "--strict"])

    assert plain.exit_code == ExitCode.OK
    assert _rule_ids(plain.stdout) == {"policy/requirement-needs-behavior"}
    assert strict.exit_code == ExitCode.FINDINGS


# --- formats and the --json fold ----------------------------------------------


def test_format_json_is_the_envelope_not_the_rendered_text() -> None:
    result = runner.invoke(app, ["--store", str(FIXTURES / "broken"), "check", "--format", "json"])

    assert result.exit_code == ExitCode.FINDINGS
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert {finding["rule_id"] for finding in payload["findings"]} == BROKEN_RULES


def test_json_on_either_side_of_the_command_matches_an_explicit_format_json() -> None:
    """The ADR-0001 fold, on a command that now has a body: `--json` before or
    after the command name is the json member of `--format`, and nothing else."""
    explicit = runner.invoke(
        app, ["--store", str(FIXTURES / "broken"), "check", "--format", "json"]
    ).stdout
    ahead = runner.invoke(app, ["--json", "--store", str(FIXTURES / "broken"), "check"]).stdout
    behind = runner.invoke(app, ["--store", str(FIXTURES / "broken"), "check", "--json"]).stdout

    assert ahead == behind == explicit


def test_an_explicit_format_beats_json() -> None:
    """`--json` is a shorthand, never an override: an explicitly passed
    `--format text` renders text even next to `--json`."""
    result = runner.invoke(
        app, ["--store", str(FIXTURES / "broken"), "check", "--json", "--format", "text"]
    )

    assert result.exit_code == ExitCode.FINDINGS
    assert not result.stdout.startswith("{")
    assert "schema/yaml-syntax" in result.stdout


def test_format_sarif_reaches_the_sarif_renderer() -> None:
    """The SARIF shape itself is `04-findings`'s to pin; what matters here is
    that the flag selects that renderer and not `render_text()`."""
    result = runner.invoke(app, ["--store", str(FIXTURES / "broken"), "check", "--format", "sarif"])

    assert result.exit_code == ExitCode.FINDINGS
    payload = json.loads(result.stdout)
    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["tool"]["driver"]["name"] == "absicht"
    assert {finding["ruleId"] for finding in payload["runs"][0]["results"]} == BROKEN_RULES


# --- --changed-only ------------------------------------------------------------


def _run_git(repo: Path, *args: str) -> None:
    """Fixture plumbing: build the throwaway repo, failing loudly if git does."""
    subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=True,
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repo (the `tests/test_git.py` shape) holding `broken/` as
    its store, on a branch whose one commit touches a single element's file.

    The touched file is the expired external's: its finding must survive the
    diff filter while everything sourced elsewhere drops.
    """
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "broken", repo / ".absicht")
    _run_git(repo, "init", "-q", "-b", "main")
    # Commits must work with no global git identity (a bare CI machine) and
    # must not try to sign.
    _run_git(repo, "config", "user.email", "tests@absicht.invalid")
    _run_git(repo, "config", "user.name", "absicht tests")
    _run_git(repo, "config", "commit.gpgsign", "false")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-qm", "the store")
    _run_git(repo, "checkout", "-q", "-b", "feature")
    expired = repo / ".absicht" / "externals" / "expired.md"
    expired.write_text(
        expired.read_text(encoding="utf-8") + "\nre-checked, still expired.\n", encoding="utf-8"
    )
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-qm", "touch one element")
    # `check` reads both the store and the diff relative to the cwd, and the
    # store must come from the repo, not whatever $ABSICHT_STORE names outside.
    monkeypatch.chdir(repo)
    monkeypatch.delenv("ABSICHT_STORE", raising=False)
    return repo


def test_changed_only_keeps_findings_about_the_diff_and_the_sourceless_ones(
    repo: Path,
) -> None:
    """The diff names `.absicht/externals/expired.md` only: findings about
    every other element drop — findings carry store-relative sources, the
    diff repo-relative paths, and the two must join — while the three cycle
    findings, which have no file to attribute, survive: the failure mode the
    task pins as the safer default for a checker. The addendum's composition
    and supersession cycles are sourceless exactly like `contains`."""
    result = runner.invoke(app, ["check", "--changed-only", "--diff-base", "main"])

    assert result.exit_code == ExitCode.FINDINGS  # every kept cycle is an error
    assert _rule_ids(result.stdout) == {
        "policy/external-assumptions-expired",
        "integrity/cycle",
        "integrity/composition-cycle",
        "integrity/supersession-cycle",
    }


def test_changed_only_with_an_unknown_base_is_a_usage_error(repo: Path) -> None:
    """A ref git cannot resolve is a broken invocation, not a finding: CI
    reads `2` as a broken pipeline and `1` as a real result about the design."""
    result = runner.invoke(app, ["check", "--changed-only", "--diff-base", "no-such-ref"])

    assert result.exit_code == ExitCode.USAGE
    assert "no-such-ref" in result.stderr


def test_changed_only_refuses_a_store_outside_the_repository(repo: Path) -> None:
    """The diff cannot name a store it does not contain, and pretending it
    checked anything would be a silent pass — the one outcome a checker must
    never fake."""
    result = runner.invoke(
        app,
        ["--store", str(FIXTURES / "broken"), "check", "--changed-only", "--diff-base", "main"],
    )

    assert result.exit_code == ExitCode.USAGE
    assert "outside" in result.stderr


# --- --explain and the failure modes that are not findings ---------------------


def test_explain_prints_the_rules_reasoning_without_reading_a_store(tmp_path: Path) -> None:
    """`--explain` short-circuits everything, the store included: the question
    is about the rule, not about this design — so a store that does not exist
    is not an error either."""
    result = runner.invoke(
        app,
        [
            "--store",
            str(tmp_path / "nowhere"),
            "check",
            "--explain",
            "policy/one-way-needs-rationale",
        ],
    )

    assert result.exit_code == ExitCode.OK
    assert RULES["policy/one-way-needs-rationale"] in result.stdout


def test_explain_json_speaks_the_envelope() -> None:
    result = runner.invoke(app, ["check", "--explain", "integrity/cycle", "--json"])

    assert result.exit_code == ExitCode.OK
    assert json.loads(result.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "rule": "integrity/cycle",
        "explain": RULES["integrity/cycle"],
    }


def test_explain_of_an_unknown_rule_is_a_usage_error() -> None:
    result = runner.invoke(app, ["check", "--explain", "policy/not-a-rule"])

    assert result.exit_code == ExitCode.USAGE
    assert "policy/not-a-rule" in result.stderr


@pytest.mark.parametrize("rule_id", ADDENDUM_RULES)
def test_explain_answers_for_every_addendum_rule(rule_id: str) -> None:
    """The pinned table's whole inventory, including the three ids enforced
    upstream: an id `--explain` cannot answer for is a silent gap in the one
    command whose job is to answer, emitted or not — the reason the
    handled-upstream ids are registered rather than dropped."""

    result = runner.invoke(app, ["check", "--explain", rule_id])

    assert result.exit_code == ExitCode.OK
    assert RULES[rule_id] in result.stdout


def test_no_store_at_all_is_a_usage_error(tmp_path: Path) -> None:
    """A missing store is a broken invocation in the exit-code table, not a
    finding about a design."""
    result = runner.invoke(app, ["--store", str(tmp_path / "nothing"), "check"])

    assert result.exit_code == ExitCode.USAGE
    assert "no store" in result.stderr


def test_a_store_without_a_system_reports_it_and_exits_findings(tmp_path: Path) -> None:
    """The one store `resolve` refuses to fold: the schema findings stand
    alone as the report rather than turning a system-wide problem into
    silence."""
    (tmp_path / "requirements").mkdir()

    result = runner.invoke(app, ["--store", str(tmp_path), "check"])

    assert result.exit_code == ExitCode.FINDINGS
    assert _rule_ids(result.stdout) == {"schema/system-missing"}
