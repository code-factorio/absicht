"""``ab migrate``: the harness, with nothing to migrate through it yet.

Schema version 1 is the only version that has ever existed, so what these
tests pin is the seam (docs/tasks/17-migrate.md): a store the binary can read
is already current and stays byte-identical — dry-run or not, since there is
no migration to run — and a target with no registered migration path is a
usage error naming the version the walk got stuck on, not a crash.

Every case goes through the CLI because the contract under test is the exit
code, the report and the files left on disk. The store is a fixture system
copied into ``tmp_path``, so a command that ever starts writing cannot
corrupt the shared fixtures.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import absicht.migrate
from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.models import SCHEMA_VERSION

runner = CliRunner()

CLEAN = Path(__file__).parent / "fixtures" / "systems" / "clean"


def store(tmp_path: Path) -> Path:
    """The clean fixture system as a private copy under ``tmp_path``."""
    copied = tmp_path / "store"
    shutil.copytree(CLEAN, copied)
    return copied


def snapshot(root: Path) -> dict[Path, bytes]:
    """Every file in the store, by store-relative path, as bytes."""
    return {
        path.relative_to(root): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_a_store_at_the_running_schema_version_is_already_current(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--store", str(store(tmp_path)), "migrate"])

    assert result.exit_code == ExitCode.OK
    assert "already current" in result.stdout


@pytest.mark.parametrize("dry_run", [["--dry-run"], []], ids=["dry-run", "for-real"])
def test_nothing_is_written_with_the_registry_empty(tmp_path: Path, dry_run: list[str]) -> None:
    """With no migration to run, dry-run and the real thing are the same run."""
    copied = store(tmp_path)
    before = snapshot(copied)

    result = runner.invoke(app, ["--store", str(copied), "migrate", *dry_run])

    assert result.exit_code == ExitCode.OK
    assert snapshot(copied) == before


def test_a_target_with_no_registered_path_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--store", str(store(tmp_path)), "migrate", "--to", "99"])

    assert result.exit_code == ExitCode.USAGE
    assert f"don't know how to migrate from {SCHEMA_VERSION}" in result.stderr
    assert result.stdout == ""


def test_a_target_older_than_the_store_is_a_usage_error(tmp_path: Path) -> None:
    """There is no downgrade: pretending the store moved back would be the
    silent wrong answer this tool exists to prevent."""
    result = runner.invoke(app, ["--store", str(store(tmp_path)), "migrate", "--to", "0"])

    assert result.exit_code == ExitCode.USAGE
    assert "older" in result.stderr
    assert result.stdout == ""


def test_migrating_without_a_store_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--store", str(tmp_path / "nowhere"), "migrate"])

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""


def test_json_output_reports_the_versions_it_moved_between(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--store", str(store(tmp_path)), "migrate", "--json"])

    assert result.exit_code == ExitCode.OK
    assert json.loads(result.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "from": SCHEMA_VERSION,
        "to": SCHEMA_VERSION,
    }


def test_json_is_accepted_on_either_side_of_the_command(tmp_path: Path) -> None:
    """`ab migrate --json`, not only `ab --json migrate`. See docs/adr/0001.

    This command's replacement for the whole-surface fold test in
    test_cli.py, which only works while a command has no body.
    """
    ahead = runner.invoke(app, ["--json", "--store", str(store(tmp_path / "a")), "migrate"])
    behind = runner.invoke(app, ["--store", str(store(tmp_path / "b")), "migrate", "--json"])

    assert ahead.exit_code == ExitCode.OK
    assert behind.exit_code == ExitCode.OK
    assert json.loads(ahead.stdout)["to"] == SCHEMA_VERSION
    assert json.loads(behind.stdout)["to"] == SCHEMA_VERSION


def test_a_fully_registered_path_refuses_loudly_rather_than_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The registry's first real entry arrives with the applier that runs it.

    Until then, a complete path can only mean one was registered without one —
    a bug in ``ab`` itself, so ``INTERNAL``, never a quiet success that moved
    nothing.
    """
    monkeypatch.setattr(absicht.migrate, "MIGRATIONS", {SCHEMA_VERSION: lambda record: record})

    result = runner.invoke(app, ["--store", str(store(tmp_path)), "migrate", "--to", "2"])

    assert result.exit_code == ExitCode.INTERNAL
    assert result.stdout == ""
