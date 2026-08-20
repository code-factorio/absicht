"""``ab schema``: regenerate the JSON Schema files a store's files validate against.

Every case goes through the CLI because the contract under test is the exit
code and the bytes on disk, not a library function shape. ``--out`` always
names a ``tmp_path`` so no case writes into the working directory: the
default ``schema/`` is the repo's own committed copy, and a test regenerating
it would both dirty the tree and hide a determinism bug behind whatever was
committed last.

One file per kind of file a store can hold, named after the store directory
that holds it (``components.schema.json`` for ``components/``), plus the three
singletons ``design``, ``layout`` and ``marker`` — the two halves of
``absicht.schema``'s map, whose directory half is read off ``absicht.codec``
rather than kept as a second list. A kind added to the store therefore gets
its schema file with nothing to forget, and the set is pinned here so it grows
by an edit and never by drifting.

What a file describes is the *document*, not the model: an element's front
matter may carry ``relates``, which the model itself forbids because an
assembled edge lives on the ``Design``. An editor told only about the model
would flag every authored relationship as an error, so the generated schema
admits the key — and only for the files that can hold one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.models.design import FORMAT_VERSION

runner = CliRunner()

DIRECTORY_FILES = {
    "glossary.schema.json",
    "actors.schema.json",
    "goals.schema.json",
    "requirements.schema.json",
    "qualities.schema.json",
    "constraints.schema.json",
    "behaviors.schema.json",
    "components.schema.json",
    "interfaces.schema.json",
    "data_entities.schema.json",
    "resources.schema.json",
    "libraries.schema.json",
    "external_services.schema.json",
    "assumptions.schema.json",
    "decisions.schema.json",
    "questions.schema.json",
    "rejections.schema.json",
    "milestones.schema.json",
    "notes.schema.json",
}
"""One per entry of `codec.DIRECTORIES`, in the store's own spelling: the file
name is the directory name is the `Design` field name."""

SINGLETON_FILES = {
    "design.schema.json",
    "layout.schema.json",
    "marker.schema.json",
}
"""The files a store holds one of, which have no directory to be named after.
A repo's `.absicht` marker is held by no store at all and still needs a
schema, which is why the three are named beside the walk rather than in it."""

EXPECTED_FILES = DIRECTORY_FILES | SINGLETON_FILES
"""The walk's whole output, pinned. A kind added to the store fails here until
its schema file lands — the set grows by editing this, not by drifting."""

ELEMENT_FILES = DIRECTORY_FILES - {"notes.schema.json"}
"""The files whose record is an `Element`, and so may carry a `relates` block.
A note is a `Record` and not an `Element`: it holds no outgoing edges, so its
document is exactly its model."""


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


def test_an_elements_document_admits_the_relates_block_its_model_refuses(tmp_path: Path) -> None:
    """The one thing an element's file holds that its model does not.

    `relates` is how a store keeps an element's outgoing edges beside the
    element, while the model keeps them in one list on the `Design` so two
    files can never disagree about a link. An editor validating the file has
    to be told about the key, or authoring an edge reads as an error.
    """
    out = tmp_path / "schema"
    _write(out)

    for name in sorted(ELEMENT_FILES):
        document = json.loads((out / name).read_text(encoding="utf-8"))
        assert "relates" in document["properties"], name
        assert document["properties"]["relates"]["default"] == [], name


@pytest.mark.parametrize("name", sorted(EXPECTED_FILES - ELEMENT_FILES))
def test_a_file_that_owns_no_edges_gets_no_relates_key(name: str, tmp_path: Path) -> None:
    """The other half of the same decision: a note and the three singletons
    are not elements, so admitting `relates` there would invite an author to
    write an edge nothing ever assembles."""
    out = tmp_path / "schema"
    _write(out)

    document = json.loads((out / name).read_text(encoding="utf-8"))

    assert "relates" not in document["properties"]


def test_nested_records_ride_along_so_every_file_is_self_contained(tmp_path: Path) -> None:
    """A schema file is handed to an editor on its own, so a `$ref` into
    another file would resolve to nothing. Each parent carries its children in
    `$defs` instead: an observation inside a behavior, an operation inside an
    interface, and the `relates` entry the document layer added."""
    out = tmp_path / "schema"
    _write(out)

    behaviors = json.loads((out / "behaviors.schema.json").read_text(encoding="utf-8"))
    interfaces = json.loads((out / "interfaces.schema.json").read_text(encoding="utf-8"))

    assert "Observation" in behaviors["$defs"]
    assert "Relates" in behaviors["$defs"]
    assert "Operation" in interfaces["$defs"]


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
    (out / "design.schema.json").unlink()

    check = runner.invoke(app, ["schema", "--out", str(out), "--check"])

    assert check.exit_code == ExitCode.FINDINGS
    assert "design.schema.json" in check.stdout


def test_check_names_a_leftover_file_no_model_generates_anymore(tmp_path: Path) -> None:
    """A kind removed from the store must leave its old schema file stale, not ignored."""
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
    (out / "interfaces.schema.json").write_text("{}\n", encoding="utf-8")
    _write(tmp_path / "fresh")

    wrote = runner.invoke(app, ["schema", "--out", str(tmp_path / "elsewhere"), "--json"])
    fresh = runner.invoke(app, ["schema", "--out", str(tmp_path / "fresh"), "--check", "--json"])
    stale = runner.invoke(app, ["schema", "--out", str(out), "--check", "--json"])

    assert wrote.exit_code == ExitCode.OK
    assert fresh.exit_code == ExitCode.OK
    assert stale.exit_code == ExitCode.FINDINGS
    wrote_payload = json.loads(wrote.stdout)
    assert wrote_payload["format_version"] == FORMAT_VERSION
    assert wrote_payload["out"] == str(tmp_path / "elsewhere")
    assert sorted(wrote_payload["wrote"]) == sorted(EXPECTED_FILES)
    assert json.loads(fresh.stdout) == {
        "format_version": FORMAT_VERSION,
        "out": str(tmp_path / "fresh"),
        "stale": [],
    }
    assert json.loads(stale.stdout) == {
        "format_version": FORMAT_VERSION,
        "out": str(out),
        "stale": ["interfaces.schema.json"],
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
