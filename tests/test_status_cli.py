"""``ab status``: where the code stands against the design.

What these tests pin, per docs/tasks/42-status.md, against the composite
fixture in a throwaway git repo (the pattern of tests/test_marker_cli.py:
watermarks name design revs, so the design must sit in a repository that is
not this repository's own history):

- a unit with a stale watermark reports the decision and interface changes
  that landed since it, and one stamped at design head reports clean;
- a never-stamped watermark is behind by everything: the empty tree is the
  base, not an error;
- an interface whose caller's watermark predates the change while the
  declaring side's does not is reported as a consumer that has not caught up;
- ``--behind-only`` drops the clean units, ``--unit`` restricts to one (an
  unknown one is ``USAGE``), ``--since`` compares against the named rev rather
  than head;
- ``--fail-on-drift`` flips the exit code exactly when drift exists;
- reference mode without ``--repo`` is ``USAGE``: a marker names repos by
  suffix and cannot enumerate them;
- embedded mode, against the clean fixture: implementation coverage and unmet
  ``done_when``, never watermarks, with the reference-mode flags no-ops that
  say so on stderr rather than silently;
- the store's own files are not evidence of a claim (a behavior names its own
  observations), while a file in an implementing repo that references an
  observation is — the weaker, claim-shaped half of ``ab verify``'s done-when
  rule.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.codec import dump_singleton, parse_singleton
from absicht.models.design import FORMAT_VERSION
from absicht.models.marker import Marker, Watermark

runner = CliRunner()

COMPOSITE = Path(__file__).parent / "fixtures" / "systems" / "composite"
CLEAN = Path(__file__).parent / "fixtures" / "systems" / "clean"

_FIRST_DECISION = """---
id: decision:invoice-format
title: Invoice format
state: specified
choice: An invoice is a PDF with a machine-readable header.
applies_to:
- component:billing-worker
---
"""

_LATER_DECISION = """---
id: decision:invoice-cadence
title: Invoice cadence
state: specified
choice: One invoice per settled order, never batched.
applies_to:
- component:billing-worker
---
"""


def _git(repo: Path, *args: str) -> str:
    """Fixture plumbing, in tests/test_marker_cli.py's shape: build and probe
    the throwaway design repo, failing loudly if git does."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def reference(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """A reference-mode world: the composite fixture under git in three
    commits, and the two implementing repos it names, each synced a marker and
    one of them stamped a rev behind head.

    c1 holds the store as copied; c2 rewrites the interface's front matter; c3
    adds the later decision. ``billing``'s watermark is stamped at c1 — stale
    by both later commits — while ``orders``'s is stamped at head, so the
    report's two halves (behind, clean) and its consumer lag (declaring side
    current, caller behind) all exist at once.
    """
    design = tmp_path / "design"
    shutil.copytree(COMPOSITE, design)
    (design / "decisions").mkdir()
    (design / "decisions" / "invoice-format.md").write_text(_FIRST_DECISION, encoding="utf-8")
    _git(design, "init", "-q", "-b", "main")
    # A bare CI machine has no git identity, and commits must not try to sign.
    _git(design, "config", "user.email", "tests@absicht.invalid")
    _git(design, "config", "user.name", "absicht tests")
    _git(design, "config", "commit.gpgsign", "false")
    _git(design, "add", "-A")
    _git(design, "commit", "-qm", "the design")
    revs = {"first": _git(design, "rev-parse", "HEAD").strip()}

    orders = tmp_path / "acme" / "orders"
    billing = tmp_path / "acme" / "billing"
    orders.mkdir(parents=True)
    billing.mkdir(parents=True)
    for repo in (orders, billing):
        assert _sync(design, repo).exit_code == ExitCode.OK
    assert _stamp(design, billing, "component:billing-worker").exit_code == ExitCode.OK

    interface = design / "interfaces" / "invoice-events.md"
    interface.write_text(
        interface.read_text(encoding="utf-8").replace(
            "implemented_by:", "failure_modes:\n- at-least-once redelivery\nimplemented_by:"
        ),
        encoding="utf-8",
    )
    _git(design, "add", "-A")
    _git(design, "commit", "-qm", "the interface moved")
    revs["second"] = _git(design, "rev-parse", "HEAD").strip()

    (design / "decisions" / "invoice-cadence.md").write_text(_LATER_DECISION, encoding="utf-8")
    _git(design, "add", "-A")
    _git(design, "commit", "-qm", "a later decision")
    revs["head"] = _git(design, "rev-parse", "HEAD").strip()
    assert _stamp(design, orders, "component:orders-api").exit_code == ExitCode.OK
    return orders, billing, revs


def _sync(design: Path, repo: Path) -> Any:
    return runner.invoke(app, ["--store", str(design), "marker", "sync", "--repo", str(repo)])


def _stamp(design: Path, repo: Path, unit: str) -> Any:
    return runner.invoke(
        app,
        [
            "--store",
            str(design),
            "marker",
            "stamp",
            "--repo",
            str(repo),
            "--unit",
            unit,
            "--milestone",
            "milestone:invoicing",
        ],
    )


def _marker(repo: Path) -> Marker:
    return parse_singleton((repo / ".absicht").read_text(encoding="utf-8"), model=Marker)


def _status(store: Path, *flags: str) -> Any:
    return runner.invoke(app, ["--store", str(store), "status", *flags])


def _reference_status(orders: Path, billing: Path, *flags: str) -> Any:
    """The invocation CI makes: sitting in an implementing repo, whose marker
    is the store location, naming every implementing repo."""
    return _status(orders / ".absicht", "--repo", str(orders), "--repo", str(billing), *flags)


# --- reference mode: watermarks -------------------------------------------------


def test_a_stale_watermark_reports_what_landed_since_it_and_a_current_one_is_clean(
    reference: tuple[Path, Path, dict[str, str]],
) -> None:
    """The stale unit lists the decision and interface changes that landed
    since its watermark — only those touching it, which is why the decision
    already in the store at the watermark does not appear — while the unit
    stamped at head reports current."""
    orders, billing, revs = reference

    result = _reference_status(orders, billing)

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        f"current: component:orders-api in {orders}",
        "behind: component:billing-worker in "
        f"{billing}: decision:invoice-cadence, interface:invoice-events "
        f"since {revs['first'][:7]}",
        "consumer behind: interface:invoice-events: component:billing-worker in "
        f"{billing} has not caught up; provider component:orders-api is current",
        "no implementation: component:acme",
        "done_when unmet: milestone:invoicing behavior:order-settles#obs-2: "
        "nothing claims to verify it",
    ]


def test_a_never_stamped_watermark_is_behind_by_everything(
    reference: tuple[Path, Path, dict[str, str]],
) -> None:
    """A marker fresh from sync carries no rev: nothing has landed, so the
    comparison base is the empty tree and every decision and interface change
    ever is unlanded — not an error, and spelled as never stamped."""
    orders, billing, _ = reference
    (billing / ".absicht").write_text(
        dump_singleton(
            Marker(
                design=_marker(billing).design,
                units=(Watermark(id="component:billing-worker", path="worker"),),
            )
        ),
        encoding="utf-8",
    )

    result = _reference_status(orders, billing)

    assert result.exit_code == ExitCode.OK
    assert (
        f"behind: component:billing-worker in {billing}: decision:invoice-cadence, "
        "decision:invoice-format, interface:invoice-events (never stamped)"
    ) in result.stdout.splitlines()


def test_behind_only_drops_the_clean_units(
    reference: tuple[Path, Path, dict[str, str]],
) -> None:
    orders, billing, _ = reference

    result = _reference_status(orders, billing, "--behind-only")

    assert result.exit_code == ExitCode.OK
    assert f"current: component:orders-api in {orders}" not in result.stdout.splitlines()
    assert f"behind: component:billing-worker in {billing}" in result.stdout


def test_unit_restricts_to_one_watermark(
    reference: tuple[Path, Path, dict[str, str]],
) -> None:
    """One unit's report only; an unknown one is a broken invocation, not an
    empty answer a script would read as "nothing to do"."""
    orders, billing, revs = reference

    result = _reference_status(orders, billing, "--unit", "component:billing-worker")
    ghost = _reference_status(orders, billing, "--unit", "component:ghost")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "behind: component:billing-worker in "
        f"{billing}: decision:invoice-cadence, interface:invoice-events "
        f"since {revs['first'][:7]}",
        "consumer behind: interface:invoice-events: component:billing-worker in "
        f"{billing} has not caught up; provider component:orders-api is current",
        # Coverage stays store-wide: --unit restricts the watermark half.
        "no implementation: component:acme",
        "done_when unmet: milestone:invoicing behavior:order-settles#obs-2: "
        "nothing claims to verify it",
    ]
    assert ghost.exit_code == ExitCode.USAGE
    assert "component:ghost" in ghost.stderr
    assert ghost.stdout == ""


def test_since_compares_against_the_named_rev_not_head(
    reference: tuple[Path, Path, dict[str, str]],
) -> None:
    """``--since c2`` narrows the comparison window to c1..c2, so the decision
    that landed in c3 drops out of the stale unit's list."""
    orders, billing, revs = reference

    result = _reference_status(orders, billing, "--since", revs["second"])

    assert result.exit_code == ExitCode.OK
    assert (
        f"behind: component:billing-worker in {billing}: "
        f"interface:invoice-events since {revs['first'][:7]}"
    ) in result.stdout.splitlines()
    assert "decision:invoice-cadence" not in result.stdout


def test_fail_on_drift_flips_the_exit_code_exactly_when_drift_exists(
    reference: tuple[Path, Path, dict[str, str]],
) -> None:
    """A report is information and exits OK; the flag is what makes drift a
    verdict, and a clean unit under the same flag stays OK."""
    orders, billing, _ = reference

    plain = _reference_status(orders, billing)
    flagged = _reference_status(orders, billing, "--fail-on-drift")
    clean = _reference_status(orders, billing, "--unit", "component:orders-api", "--fail-on-drift")

    assert plain.exit_code == ExitCode.OK
    assert flagged.exit_code == ExitCode.FINDINGS
    assert flagged.stdout == plain.stdout
    assert clean.exit_code == ExitCode.OK


def test_json_envelopes_the_report(reference: tuple[Path, Path, dict[str, str]]) -> None:
    orders, billing, revs = reference

    result = _reference_status(orders, billing, "--format", "json")

    assert result.exit_code == ExitCode.OK
    assert json.loads(result.stdout) == {
        "format_version": FORMAT_VERSION,
        "mode": "reference",
        "against": revs["head"],
        "units": [
            {
                "repo": str(orders),
                "id": "component:orders-api",
                "path": "api",
                "at": "milestone:invoicing",
                "design_rev": revs["head"],
                "decisions": [],
                "interfaces": [],
            },
            {
                "repo": str(billing),
                "id": "component:billing-worker",
                "path": "worker",
                "at": "milestone:invoicing",
                "design_rev": revs["first"],
                "decisions": ["decision:invoice-cadence"],
                "interfaces": ["interface:invoice-events"],
            },
        ],
        "consumers_behind": [
            {
                "interface": "interface:invoice-events",
                "consumer": "component:billing-worker",
                "repo": str(billing),
                "provider": "component:orders-api",
            }
        ],
        "no_implementation": ["component:acme"],
        "done_when_unmet": [
            {"milestone": "milestone:invoicing", "observation": "behavior:order-settles#obs-2"}
        ],
    }


def test_reference_mode_without_repo_is_a_usage_error(
    reference: tuple[Path, Path, dict[str, str]],
) -> None:
    """A marker names repos by suffix, which cannot locate them on disk:
    reference mode needs the repos named outright."""
    orders, _, _ = reference

    result = _status(orders / ".absicht")

    assert result.exit_code == ExitCode.USAGE
    assert "--repo" in result.stderr
    assert result.stdout == ""


# --- embedded mode: coverage ----------------------------------------------------


def test_embedded_reports_coverage_and_done_when_without_watermarks(
    tmp_path: Path,
) -> None:
    """Embedded, design and code land in the same commit and nothing can be
    behind: implementation coverage and unmet ``done_when`` is the whole
    report, watermarks are never mentioned, and the reference-mode flags are
    no-ops that say so on stderr rather than silently."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)

    result = _status(store)
    flagged = _status(store, "--repo", str(tmp_path), "--fail-on-drift")
    as_json = _status(store, "--json")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "no implementation: component:acme",
        "done_when unmet: milestone:m1 behavior:order-cancelled#obs-1: nothing claims to verify it",
    ]
    assert "watermark" not in result.stdout
    assert flagged.exit_code == ExitCode.OK
    assert flagged.stdout == result.stdout
    assert "embedded" in flagged.stderr
    assert "--repo" in flagged.stderr
    assert "--fail-on-drift" in flagged.stderr
    assert json.loads(as_json.stdout)["mode"] == "embedded"


def test_claims_are_looked_for_outside_the_store(tmp_path: Path) -> None:
    """The weaker half of ``ab verify``'s done-when rule: a claim is a file in
    the repo referencing the observation id. The store's own files do not count
    — a behavior names its own observations, and counting that would make
    ``done_when`` vacuously pass — while a step-definition-shaped file beside
    it does."""
    repo = tmp_path / "repo"
    store = repo / "store"
    shutil.copytree(CLEAN, store)
    _git(repo, "init", "-q")

    bare = _status(store)
    (repo / "test_cancellation.py").write_text(
        '"""behavior:order-cancelled#obs-1"""\n', encoding="utf-8"
    )
    claimed = _status(store)

    assert bare.exit_code == ExitCode.OK
    assert "done_when unmet: milestone:m1 behavior:order-cancelled#obs-1" in bare.stdout
    assert claimed.exit_code == ExitCode.OK
    assert "done_when unmet" not in claimed.stdout
    assert claimed.stdout.splitlines() == [
        "no implementation: component:acme",
    ]


def test_the_store_skip_holds_for_a_relative_store_path_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default invocation spells ``--store`` relatively (``.absicht``, or a
    bare directory name), and the claim scan walks files git spells absolutely:
    a skip compared across those two spellings never fires, so the store claims
    its own observations and ``done_when`` reads vacuously met — absicht's own
    store reported every observation met the first time ``ab status`` ran
    against it. The skip has to hold for the relative spelling, not just the
    absolute one the tests happened to use."""
    repo = tmp_path / "repo"
    shutil.copytree(CLEAN, repo / "store")
    _git(repo, "init", "-q")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["--store", "store", "status"])

    assert result.exit_code == ExitCode.OK
    assert "done_when unmet: milestone:m1 behavior:order-cancelled#obs-1" in result.stdout


def test_an_observation_claimed_in_an_implementing_repo_is_met(
    reference: tuple[Path, Path, dict[str, str]],
) -> None:
    """Reference mode looks for claims where the code lives: the implementing
    repos, not the design store."""
    orders, billing, _ = reference
    (billing / "test_invoicing.py").write_text(
        '"""behavior:order-settles#obs-2"""\n', encoding="utf-8"
    )

    result = _reference_status(orders, billing)

    assert result.exit_code == ExitCode.OK
    assert "done_when unmet" not in result.stdout
