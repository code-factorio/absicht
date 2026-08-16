"""``ab marker sync --repo PATH`` and ``ab marker check --repo PATH``: write a
repo's discovery marker, then hold it to what the store says.

What the sync tests pin, per docs/tasks/44-marker-sync.md, against the
composite fixture (the multi-repo system it was built for):

- the marker written names the fixture's units for that repo, and the design
  URL it carries is one absicht's own store resolution can follow back to the
  store the sync ran against — the discovery round trip, closed;
- a watermark already in the marker survives a resync;
- a ``.absicht/`` directory at the repo root is ``USAGE``: sync never converts
  a store's own repo into a marker-holding one;
- ``--json`` is the ``schema_version`` envelope of docs/tasks/00-conventions.md,
  on either side of the command name (docs/adr/0001).

What the check tests pin, per docs/tasks/45-marker-check.md:

- a marker fresh from sync passes silent; one the design has moved on from
  (a unit gained, a unit at a stale path) is ``FINDINGS`` naming the unit;
- a repo without a marker and an embedded repo are both ``USAGE``, each in
  its own words.

What the stamp tests pin, per docs/tasks/46-marker-stamp.md, against the
composite fixture copied into a throwaway git repo (the pattern of
tests/test_git.py, since ``design_rev`` is the design store's HEAD — it must
come from a repo that is not this repository's own history):

- a tracked unit's watermark moves to the milestone asked for and the design
  head at invocation time, with the rest of the marker untouched;
- an untracked unit, a repo with no marker, a milestone the store does not
  have: each ``USAGE``, in its own words;
- ``--json`` is the same ``schema_version`` envelope sync writes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.codec import dump_singleton, parse_singleton
from absicht.load import resolve_store
from absicht.models import SCHEMA_VERSION, Marker, UnitWatermark

runner = CliRunner()

STORE = Path(__file__).parent / "fixtures" / "systems" / "composite"

_MILESTONE = """---
id: milestone:m1
title: Orders v1
state: specified
---
"""
"""The milestone the stamp tests land at: the composite fixture ships none,
and a stamp needs a milestone the store actually has."""


def _repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True)
    return repo


def _sync(repo: Path, *flags: str, store: Path = STORE) -> Any:
    return runner.invoke(
        app, ["--store", str(store), "marker", "sync", "--repo", str(repo), *flags]
    )


def _marker(repo: Path) -> Marker:
    return parse_singleton((repo / ".absicht").read_text(encoding="utf-8"), model=Marker)


def _check(repo: Path, *flags: str, store: Path = STORE) -> Any:
    return runner.invoke(
        app, ["--store", str(store), "marker", "check", "--repo", str(repo), *flags]
    )


def _at_a_stale_path(repo: Path, path: str) -> None:
    """Rewrite the repo's marker with its unit at another path — the shape a
    component move leaves behind when nobody resyncs."""
    (repo / ".absicht").write_text(
        dump_singleton(
            Marker(
                design=_marker(repo).design,
                units=(UnitWatermark(id="component:orders-api", path=path),),
            )
        ),
        encoding="utf-8",
    )


def _run_git(repo: Path, *args: str) -> str:
    """Fixture plumbing, in tests/test_git.py's shape: build and probe the
    throwaway design repo, failing loudly if git does."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _store_under_git(tmp_path: Path) -> Path:
    """The composite fixture in a throwaway git repo, with the stamp tests'
    milestone added: `design_rev` is the design store's HEAD, so the store
    must sit in a repository that is not this repository's own."""
    store = tmp_path / "design"
    shutil.copytree(STORE, store)
    (store / "milestones").mkdir()
    (store / "milestones" / "m1.md").write_text(_MILESTONE, encoding="utf-8")
    _run_git(store, "init", "-q", "-b", "main")
    # Commits must work with no global git identity (a bare CI machine) and
    # must not try to sign.
    _run_git(store, "config", "user.email", "tests@absicht.invalid")
    _run_git(store, "config", "user.name", "absicht tests")
    _run_git(store, "config", "commit.gpgsign", "false")
    _run_git(store, "add", "-A")
    _run_git(store, "commit", "-q", "-m", "the design")
    return store


def _stamp(store: Path, repo: Path, unit: str, *flags: str, milestone: str = "milestone:m1") -> Any:
    return runner.invoke(
        app,
        [
            "--store",
            str(store),
            "marker",
            "stamp",
            "--repo",
            str(repo),
            "--unit",
            unit,
            "--milestone",
            milestone,
            *flags,
        ],
    )


def test_sync_writes_a_marker_that_leads_back_to_the_store(tmp_path: Path) -> None:
    """The discovery round trip: an agent dropped into the implementing repo
    reads the marker and resolves the store it names without being told where
    to look — pinned by running absicht's own store resolution over the file
    sync just wrote."""
    repo = _repo(tmp_path, "acme/orders")

    result = _sync(repo)

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [f"wrote {repo / '.absicht'} (1 unit)"]
    assert _marker(repo).units == (UnitWatermark(id="component:orders-api", path="api"),)
    assert resolve_store(repo / ".absicht") == STORE


def test_a_watermark_in_the_marker_survives_a_resync(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "acme/orders")
    assert _sync(repo).exit_code == ExitCode.OK
    stamped = Marker(
        design=_marker(repo).design,
        units=(
            UnitWatermark(
                id="component:orders-api", path="api", at="milestone:m1", design_rev="deadbeef"
            ),
        ),
    )
    (repo / ".absicht").write_text(dump_singleton(stamped), encoding="utf-8")

    result = _sync(repo)

    assert result.exit_code == ExitCode.OK
    assert _marker(repo) == stamped


def test_an_embedded_repo_is_a_usage_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "r")
    (repo / ".absicht").mkdir()

    result = _sync(repo)

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""
    assert "directory" in result.stderr
    assert list((repo / ".absicht").iterdir()) == []


def test_json_envelopes_the_units_written(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "acme/orders")

    result = _sync(repo, "--json")

    assert json.loads(result.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "out": str(repo / ".absicht"),
        "units": [{"id": "component:orders-api", "path": "api", "at": None, "design_rev": None}],
    }


def test_json_is_accepted_on_either_side_of_the_command(tmp_path: Path) -> None:
    """`ab marker sync --json`, not only `ab --json marker sync`. See
    docs/adr/0001. This command's replacement for the whole-surface fold test
    in test_cli.py, which only covers commands without a body."""
    ahead = runner.invoke(
        app,
        ["--json", "--store", str(STORE), "marker", "sync", "--repo", str(_repo(tmp_path, "a"))],
    )
    behind = _sync(_repo(tmp_path, "b"), "--json")

    assert ahead.exit_code == ExitCode.OK
    assert behind.exit_code == ExitCode.OK
    assert json.loads(ahead.stdout)["units"] == json.loads(behind.stdout)["units"]


def test_a_marker_fresh_from_sync_passes_silent(tmp_path: Path) -> None:
    """Silence is the pass signal, the spelling `ab check` uses."""
    repo = _repo(tmp_path, "acme/orders")
    assert _sync(repo).exit_code == ExitCode.OK

    result = _check(repo)

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""


def test_a_unit_the_store_gained_is_a_finding(tmp_path: Path) -> None:
    """The spec's own simulation: sync, then add an `implemented_by` entry
    to the design — a copy of the fixture, so the committed store stays
    pristine — and check without resyncing."""
    repo = _repo(tmp_path, "acme/orders")
    assert _sync(repo).exit_code == ExitCode.OK
    store = tmp_path / "design"
    shutil.copytree(STORE, store)
    component = store / "components" / "orders-api.md"
    component.write_text(
        component.read_text(encoding="utf-8").replace(
            "- acme/orders#api\n", "- acme/orders#api\n- acme/orders#api/v2\n"
        ),
        encoding="utf-8",
    )

    result = _check(repo, store=store)

    assert result.exit_code == ExitCode.FINDINGS
    (line,) = result.stdout.splitlines()
    assert "error marker/missing-unit" in line
    assert "component:orders-api" in line
    assert "api/v2" in line


def test_a_unit_at_a_stale_path_is_a_finding(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "acme/orders")
    assert _sync(repo).exit_code == ExitCode.OK
    _at_a_stale_path(repo, "api/v0")

    result = _check(repo)

    assert result.exit_code == ExitCode.FINDINGS
    (line,) = result.stdout.splitlines()
    assert "error marker/moved-unit" in line
    assert "component:orders-api" in line
    assert "api/v0" in line


def test_a_repo_without_a_marker_is_a_usage_error(tmp_path: Path) -> None:
    result = _check(_repo(tmp_path, "r"))

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""
    assert "no marker to check" in result.stderr


def test_an_embedded_repo_is_a_usage_error_for_checking_too(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "r")
    (repo / ".absicht").mkdir()

    result = _check(repo)

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""
    assert "is a directory" in result.stderr


def test_json_envelopes_the_findings(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "acme/orders")
    assert _sync(repo).exit_code == ExitCode.OK
    _at_a_stale_path(repo, "api/v0")

    result = _check(repo, "--json")

    payload = json.loads(result.stdout)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert [f["rule_id"] for f in payload["findings"]] == ["marker/moved-unit"]
    assert payload["findings"][0]["ref"] == "component:orders-api"


def test_stamp_moves_the_watermark_to_the_design_head_at_invocation_time(
    tmp_path: Path,
) -> None:
    """The evidence pair: `at` from --milestone, `design_rev` from the design
    store's HEAD *when the stamp runs* — a design commit landing between the
    sync and the stamp is the rev recorded. The implementing repo is no git
    repo at all here, so a rev read from --repo could never have produced
    this pass."""
    store = _store_under_git(tmp_path)
    repo = _repo(tmp_path, "acme/orders")
    assert _sync(repo, store=store).exit_code == ExitCode.OK
    _run_git(store, "commit", "-q", "--allow-empty", "-m", "design moved on")
    head = _run_git(store, "rev-parse", "HEAD").strip()

    result = _stamp(store, repo, "component:orders-api")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        f"stamped component:orders-api at milestone:m1 in {repo / '.absicht'}"
    ]
    assert _marker(repo).units == (
        UnitWatermark(id="component:orders-api", path="api", at="milestone:m1", design_rev=head),
    )


def test_stamping_a_unit_the_marker_does_not_carry_is_a_usage_error(tmp_path: Path) -> None:
    store = _store_under_git(tmp_path)
    repo = _repo(tmp_path, "acme/orders")
    assert _sync(repo, store=store).exit_code == ExitCode.OK

    result = _stamp(store, repo, "component:unknown")

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""
    assert "no such unit" in result.stderr


def test_stamping_a_repo_without_a_marker_is_a_usage_error(tmp_path: Path) -> None:
    store = _store_under_git(tmp_path)
    repo = _repo(tmp_path, "acme/orders")

    result = _stamp(store, repo, "component:orders-api")

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""
    assert "no marker to stamp" in result.stderr


def test_stamping_a_milestone_the_store_does_not_have_is_a_usage_error(
    tmp_path: Path,
) -> None:
    """A stamp is evidence; a claim about a milestone that does not exist is
    garbage a later `ab status` could not make sense of, so it is refused at
    the source and nothing is written."""
    store = _store_under_git(tmp_path)
    repo = _repo(tmp_path, "acme/orders")
    assert _sync(repo, store=store).exit_code == ExitCode.OK

    result = _stamp(store, repo, "component:orders-api", milestone="milestone:nowhere")

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""
    assert "no milestone" in result.stderr
    assert _marker(repo).units[0].at is None


def test_stamp_json_envelopes_the_watermark(tmp_path: Path) -> None:
    store = _store_under_git(tmp_path)
    repo = _repo(tmp_path, "acme/orders")
    assert _sync(repo, store=store).exit_code == ExitCode.OK
    head = _run_git(store, "rev-parse", "HEAD").strip()

    result = _stamp(store, repo, "component:orders-api", "--json")

    assert json.loads(result.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "out": str(repo / ".absicht"),
        "units": [
            {
                "id": "component:orders-api",
                "path": "api",
                "at": "milestone:m1",
                "design_rev": head,
            }
        ],
    }
