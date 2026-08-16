"""``ab marker sync --repo PATH``: write or update a repo's discovery marker.

What these tests pin, per docs/tasks/44-marker-sync.md, against the composite
fixture (the multi-repo system it was built for):

- the marker written names the fixture's units for that repo, and the design
  URL it carries is one absicht's own store resolution can follow back to the
  store the sync ran against — the discovery round trip, closed;
- a watermark already in the marker survives a resync;
- a ``.absicht/`` directory at the repo root is ``USAGE``: sync never converts
  a store's own repo into a marker-holding one;
- ``--json`` is the ``schema_version`` envelope of docs/tasks/00-conventions.md,
  on either side of the command name (docs/adr/0001).
"""

from __future__ import annotations

import json
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


def _repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True)
    return repo


def _sync(repo: Path, *flags: str) -> Any:
    return runner.invoke(
        app, ["--store", str(STORE), "marker", "sync", "--repo", str(repo), *flags]
    )


def _marker(repo: Path) -> Marker:
    return parse_singleton((repo / ".absicht").read_text(encoding="utf-8"), model=Marker)


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
