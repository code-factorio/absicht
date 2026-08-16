"""``ab schema``: regenerate the JSON Schema files a store's files validate against.

Every case goes through the CLI because the contract under test is the exit
code and the bytes on disk, not a library function shape. ``--out`` always
names a ``tmp_path`` so no case writes into the working directory: the
default ``schema/`` is the repo's own committed copy, and a test regenerating
it would both dirty the tree and hide a determinism bug behind whatever was
committed last.

One file per kind of file a store can hold, named after the store directory
that holds it (``components.schema.json`` for ``components/``, plus the two
singletons ``system`` and ``marker``) — the spelling pinned in
docs/tasks/00-conventions.md, where a kind *is* its directory and both match
``Design``'s field names.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.models import SCHEMA_VERSION

runner = CliRunner()

EXPECTED_FILES = {
    "system.schema.json",
    "externals.schema.json",
    "requirements.schema.json",
    "non_functionals.schema.json",
    "stories.schema.json",
    "components.schema.json",
    "seams.schema.json",
    "data.schema.json",
    "resources.schema.json",
    "behaviors.schema.json",
    "decisions.schema.json",
    "rejections.schema.json",
    "questions.schema.json",
    "milestones.schema.json",
    "marker.schema.json",
}
"""The walk's whole output, pinned. A kind added to `Design` fails here until
its schema file lands — the set grows by editing this, not by drifting."""


def _write(out: Path) -> None:
    result = runner.invoke(app, ["schema", "--out", str(out)])
    assert result.exit_code == ExitCode.OK


def test_writes_one_valid_schema_per_file_kind(tmp_path: Path) -> None:
    out = tmp_path / "schema"

    result = runner.invoke(app, ["schema", "--out", str(out)])

    assert result.exit_code == ExitCode.OK
    assert {path.name for path in out.iterdir()} == EXPECTED_FILES
    for path in out.iterdir():
        text = path.read_text(encoding="utf-8")
        # Structural checks only: the schema's job is to be usable by an
        # editor, and "parses, is an object type with properties" is that.
        document = json.loads(text)
        assert document["type"] == "object"
        assert isinstance(document["properties"], dict)
        assert text.endswith("\n")  # the committed files end where git wants


def test_check_passes_against_what_the_command_writes(tmp_path: Path) -> None:
    out = tmp_path / "schema"
    _write(out)

    check = runner.invoke(app, ["schema", "--out", str(out), "--check"])

    assert check.exit_code == ExitCode.OK
    assert "up to date" in check.stdout


def test_check_names_a_file_whose_content_drifted(tmp_path: Path) -> None:
    out = tmp_path / "schema"
    _write(out)
    drifted = out / "components.schema.json"
    drifted.write_text(drifted.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    check = runner.invoke(app, ["schema", "--out", str(out), "--check"])

    assert check.exit_code == ExitCode.FINDINGS
    assert "components.schema.json" in check.stdout


def test_check_names_a_generated_file_that_is_missing(tmp_path: Path) -> None:
    out = tmp_path / "schema"
    _write(out)
    (out / "system.schema.json").unlink()

    check = runner.invoke(app, ["schema", "--out", str(out), "--check"])

    assert check.exit_code == ExitCode.FINDINGS
    assert "system.schema.json" in check.stdout


def test_check_names_a_leftover_file_no_model_generates_anymore(tmp_path: Path) -> None:
    """A kind removed from `Design` must leave its old schema file stale, not ignored."""
    out = tmp_path / "schema"
    _write(out)
    (out / "ghosts.schema.json").write_text("{}\n", encoding="utf-8")

    check = runner.invoke(app, ["schema", "--out", str(out), "--check"])

    assert check.exit_code == ExitCode.FINDINGS
    assert "ghosts.schema.json" in check.stdout


def test_two_runs_write_byte_identical_files(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    _write(first)
    _write(second)

    for name in sorted(path.name for path in first.iterdir()):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_output_survives_a_different_hash_seed(tmp_path: Path) -> None:
    """`$defs` ordering must not leak dict iteration order across interpreters.

    The determinism standard (docs/maintainers/verification.md) asks for
    byte-identical output under varying `PYTHONHASHSEED`, which an in-process
    runner cannot reproduce: two CliRunner calls share one interpreter.
    """
    outputs = []
    for seed in ("1", "2"):
        target = tmp_path / seed
        subprocess.run(
            [sys.executable, "-m", "absicht", "schema", "--out", str(target)],
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.append(sorted((p.name, p.read_bytes()) for p in target.iterdir()))

    assert outputs[0] == outputs[1]


def test_json_output_envelopes_writes_and_stale_files(tmp_path: Path) -> None:
    out = tmp_path / "schema"
    _write(out)
    (out / "seams.schema.json").write_text("{}\n", encoding="utf-8")
    _write(tmp_path / "fresh")

    wrote = runner.invoke(app, ["schema", "--out", str(tmp_path / "elsewhere"), "--json"])
    fresh = runner.invoke(app, ["schema", "--out", str(tmp_path / "fresh"), "--check", "--json"])
    stale = runner.invoke(app, ["schema", "--out", str(out), "--check", "--json"])

    assert wrote.exit_code == ExitCode.OK
    assert fresh.exit_code == ExitCode.OK
    assert stale.exit_code == ExitCode.FINDINGS
    wrote_payload = json.loads(wrote.stdout)
    assert wrote_payload["schema_version"] == SCHEMA_VERSION
    assert wrote_payload["out"] == str(tmp_path / "elsewhere")
    assert sorted(wrote_payload["wrote"]) == sorted(EXPECTED_FILES)
    assert json.loads(fresh.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "out": str(tmp_path / "fresh"),
        "stale": [],
    }
    assert json.loads(stale.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "out": str(out),
        "stale": ["seams.schema.json"],
    }


def test_json_is_accepted_on_either_side_of_the_command(tmp_path: Path) -> None:
    """`ab schema --json`, not only `ab --json schema`. See docs/adr/0001.

    This command's replacement for the whole-surface fold test in
    test_cli.py, which only works while a command has no body: parsing stdout
    as JSON is only possible if the fold in `options()` saw the flag the
    command declared under the name it expects.
    """
    ahead = runner.invoke(app, ["--json", "schema", "--out", str(tmp_path / "a")])
    behind = runner.invoke(app, ["schema", "--out", str(tmp_path / "b"), "--json"])

    assert ahead.exit_code == ExitCode.OK
    assert behind.exit_code == ExitCode.OK
    assert json.loads(ahead.stdout)["wrote"] == json.loads(behind.stdout)["wrote"]
