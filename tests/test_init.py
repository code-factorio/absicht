"""``ab init``: scaffold a store, refusing to touch anything that already exists.

Every case goes through the CLI because the contract under test is the exit
code and the files left on disk, not a library function shape. The store is
always named with ``--store`` into ``tmp_path``, so no case depends on the
working directory.

The one subtle rule (docs/tasks/10-init.md): ``--force`` relaxes the
already-exists check only for a store nothing has been authored into. A
scaffolded ``system.yaml`` is not an element, so ``init --force`` over a fresh
scaffold succeeds — but any ``<kind>/<slug>.md`` file makes the store
non-empty and ``--force`` refuses all the same.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.codec import parse_singleton
from absicht.models import SCHEMA_VERSION, Marker, System

runner = CliRunner()

DESIGN = "https://example.com/design"


def test_embedded_init_scaffolds_a_system_and_nothing_else(tmp_path: Path) -> None:
    store = tmp_path / "store"

    result = runner.invoke(app, ["--store", str(store), "init", "--name", "ACME Orders"])

    assert result.exit_code == ExitCode.OK
    assert [path.name for path in tmp_path.iterdir()] == ["store"]
    assert [path.name for path in store.iterdir()] == ["system.yaml"]
    # The kind directories are not created: load reads a missing one as empty,
    # and the id is the slugified name per 00-conventions.md's identity rule.
    assert parse_singleton(
        (store / "system.yaml").read_text(encoding="utf-8"), model=System
    ) == System(id="system:acme-orders", title="ACME Orders")


@pytest.mark.parametrize("name", ["", "   ", "!!!"])
def test_a_name_with_no_letters_or_digits_is_a_usage_error(tmp_path: Path, name: str) -> None:
    result = runner.invoke(app, ["--store", str(tmp_path), "init", "--name", name])

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""


def test_a_second_init_without_force_is_a_usage_error(tmp_path: Path) -> None:
    argv = ["--store", str(tmp_path / "store"), "init", "--name", "ACME"]

    assert runner.invoke(app, argv).exit_code == ExitCode.OK

    again = runner.invoke(app, argv)

    assert again.exit_code == ExitCode.USAGE
    assert again.stdout == ""


def test_force_writes_into_a_scaffolded_but_empty_store(tmp_path: Path) -> None:
    store = tmp_path / "store"
    argv = ["--store", str(store), "init", "--name", "ACME"]
    assert runner.invoke(app, argv).exit_code == ExitCode.OK

    again = runner.invoke(app, [*argv, "--force"])

    assert again.exit_code == ExitCode.OK
    assert [path.name for path in store.iterdir()] == ["system.yaml"]


def test_force_still_refuses_once_the_store_has_elements(tmp_path: Path) -> None:
    store = tmp_path / "store"
    argv = ["--store", str(store), "init", "--name", "ACME"]
    assert runner.invoke(app, argv).exit_code == ExitCode.OK
    element = store / "components" / "orders.md"
    element.parent.mkdir()
    element.write_text("---\nid: component:orders\ntitle: Orders\n---\n", encoding="utf-8")

    again = runner.invoke(app, [*argv, "--force"])

    assert again.exit_code == ExitCode.USAGE
    assert "elements" in again.stderr


def test_a_marker_file_blocks_embedded_init_even_with_force(tmp_path: Path) -> None:
    marker = tmp_path / ".absicht"
    marker.write_text(f"design: {DESIGN}\n", encoding="utf-8")

    refused = runner.invoke(app, ["--store", str(marker), "init", "--name", "ACME", "--force"])

    assert refused.exit_code == ExitCode.USAGE
    assert refused.stdout == ""


def test_reference_init_writes_exactly_a_marker_file(tmp_path: Path) -> None:
    marker = tmp_path / "repo" / ".absicht"
    marker.parent.mkdir()

    result = runner.invoke(app, ["--store", str(marker), "init", "--reference", DESIGN])

    assert result.exit_code == ExitCode.OK
    assert [path.name for path in (tmp_path / "repo").iterdir()] == [".absicht"]
    assert marker.is_file()
    # `units` stays empty: `ab marker sync` is what fills them in (44-marker-sync).
    assert parse_singleton(marker.read_text(encoding="utf-8"), model=Marker) == Marker(
        design=DESIGN
    )


def test_a_reference_without_a_url_is_a_usage_error(tmp_path: Path) -> None:
    marker = tmp_path / "m"

    result = runner.invoke(app, ["--store", str(marker), "init", "--reference", "   "])

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""
    assert not marker.exists()


def test_a_store_directory_blocks_reference_init(tmp_path: Path) -> None:
    store = tmp_path / ".absicht"
    store.mkdir()

    refused = runner.invoke(app, ["--store", str(store), "init", "--reference", DESIGN])

    assert refused.exit_code == ExitCode.USAGE
    assert refused.stdout == ""
    assert list(store.iterdir()) == []


def test_embedded_and_reference_are_mutually_exclusive(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["--store", str(tmp_path), "init", "--embedded", "--reference", DESIGN]
    )

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""
    assert list(tmp_path.iterdir()) == []  # nothing was scaffolded


def test_json_output_names_the_mode_and_the_path_created(tmp_path: Path) -> None:
    store = tmp_path / "s"
    marker = tmp_path / "m"

    embedded = runner.invoke(app, ["--store", str(store), "init", "--name", "ACME", "--json"])
    reference = runner.invoke(
        app, ["--store", str(marker), "init", "--reference", DESIGN, "--json"]
    )

    assert embedded.exit_code == ExitCode.OK
    assert reference.exit_code == ExitCode.OK
    assert json.loads(embedded.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "mode": "embedded",
        "path": str(store / "system.yaml"),
    }
    assert json.loads(reference.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "mode": "reference",
        "path": str(marker),
    }


def test_json_is_accepted_on_either_side_of_the_command(tmp_path: Path) -> None:
    """`ab init --json`, not only `ab --json init`. See docs/adr/0001.

    This command's replacement for the whole-surface fold test in
    test_cli.py, which only works while a command has no body: parsing stdout
    as JSON is only possible if the fold in `options()` saw the flag the
    command declared under the name it expects.
    """
    ahead = runner.invoke(app, ["--json", "--store", str(tmp_path / "a"), "init", "--name", "A"])
    behind = runner.invoke(app, ["--store", str(tmp_path / "b"), "init", "--name", "B", "--json"])

    assert ahead.exit_code == ExitCode.OK
    assert behind.exit_code == ExitCode.OK
    assert json.loads(ahead.stdout)["mode"] == "embedded"
    assert json.loads(behind.stdout)["mode"] == "embedded"
