"""``ab new``: one element scaffolded from a template, id from the slug.

Every case goes through the CLI, as in ``test_init``: the contract under test
is the exit code, the files left on disk and what the codec reads back —
never a library function shape. The store is always named with ``--store``
into ``tmp_path``, so no case depends on the working directory.

The two refusal halves (docs/tasks/11-new.md) each get a case: an id the
loaded store already holds, and a file sitting at the path about to be
written. They are the same condition in a healthy store and different ones
once the store and the filesystem have drifted — a renamed file still
holding the old id fails the first, an unparsable file no index ever saw
fails the second.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from absicht.new import NewError, scaffold
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode, Kind
from absicht.codec import dump_element, parse_element
from absicht.load import load_store
from absicht.models import SCHEMA_VERSION, Component
from absicht.resolve import Index, resolve

runner = CliRunner()

# The three kinds whose model has a required field no default exists for, and
# the placeholder `ab new` fills it with: the enum's first declared member,
# named again in a comment in the element's body.
PLACEHOLDER: dict[str, tuple[str, str]] = {
    "seam": ("style", "call"),
    "nfr": ("attribute", "latency"),
    "external": ("external_kind", "service"),
}


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """An initialized store: `new` refuses to author into a directory that is not one."""
    root = tmp_path / "store"
    assert runner.invoke(app, ["--store", str(root), "init", "--name", "ACME"]).exit_code == (
        ExitCode.OK
    )
    return root


def new(store: Path, *argv: str) -> object:
    """`ab new` against `store`, with the common prefix elided."""
    return runner.invoke(app, ["--store", str(store), "new", *argv])


def test_new_writes_exactly_one_file_with_the_expected_front_matter(store: Path) -> None:
    result = new(
        store, "component", "cancellation-flow", "--title", "Cancellation flow", "--owner", "vinz"
    )

    assert result.exit_code == ExitCode.OK
    assert [path.name for path in store.iterdir()] == ["system.yaml", "components"]
    written = store / "components" / "cancellation-flow.md"
    assert [path.name for path in (store / "components").iterdir()] == ["cancellation-flow.md"]
    assert parse_element(
        written.read_text(encoding="utf-8"),
        model=Component,
        source="components/cancellation-flow.md",
    ) == Component(
        id="component:cancellation-flow",
        title="Cancellation flow",
        owner="vinz",
        source="components/cancellation-flow.md",
    )


def test_the_title_falls_back_to_the_slug_and_the_state_to_unknown(store: Path) -> None:
    """The two documented defaults: `--title` has none, `--state`'s is `unknown`."""
    result = new(store, "component", "orders")

    assert result.exit_code == ExitCode.OK
    element = parse_element(
        (store / "components" / "orders.md").read_text(encoding="utf-8"),
        model=Component,
        source="components/orders.md",
    )
    assert element.title == "orders"
    assert element.state.value == "unknown"


def test_print_renders_to_stdout_and_leaves_the_store_alone(store: Path) -> None:
    result = new(store, "component", "orders", "--print")

    assert result.exit_code == ExitCode.OK
    # typer.echo appends the newline; the rendering itself is exactly the file
    # text, so the command pipes into anything that reads the format.
    assert result.stdout == dump_element(Component(id="component:orders", title="orders")) + "\n"
    assert [path.name for path in store.iterdir()] == ["system.yaml"]


def test_a_slug_the_store_already_holds_is_a_usage_error_not_an_overwrite(
    store: Path,
) -> None:
    assert new(store, "component", "orders", "--title", "first").exit_code == ExitCode.OK

    again = new(store, "component", "orders", "--title", "second")

    assert again.exit_code == ExitCode.USAGE
    assert "already exists" in again.stderr
    assert "title: first" in (store / "components" / "orders.md").read_text(encoding="utf-8")


def test_an_id_held_by_a_differently_named_file_still_blocks(store: Path) -> None:
    """Store drift, first half: the index knows the id, the path does not exist."""
    drifted = store / "components" / "renamed.md"
    drifted.parent.mkdir()
    drifted.write_text("---\nid: component:orders\ntitle: Orders\n---\n", encoding="utf-8")

    result = new(store, "component", "orders")

    assert result.exit_code == ExitCode.USAGE
    assert not (store / "components" / "orders.md").exists()


def test_a_file_at_the_target_path_blocks_even_when_no_index_ever_saw_it(
    store: Path,
) -> None:
    """Store drift, second half: the path is taken, the index never read the file."""
    stray = store / "components" / "orders.md"
    stray.parent.mkdir()
    stray.write_text("not front matter at all\n", encoding="utf-8")

    result = new(store, "component", "orders")

    assert result.exit_code == ExitCode.USAGE
    assert "already exists" in result.stderr


@pytest.mark.parametrize("kind", list(Kind), ids=lambda kind: kind.value)
def test_every_kind_scaffolds_a_loadable_round_trippable_file(store: Path, kind: Kind) -> None:
    """One case per `Kind`: what `load_store` reads back is what was meant.

    This is also the guard that keeps this command's kind-to-directory table
    and `absicht.load`'s in step — an element written to a directory `load`
    does not read would simply not be here.
    """
    result = new(store, kind.value, "probe", "--title", "Probe")

    assert result.exit_code == ExitCode.OK
    loaded = load_store(store)
    assert loaded.errors == ()
    element = Index.from_design(resolve(loaded)).by_id[f"{kind.value}:probe"]
    assert element.title == "Probe"
    if kind.value in PLACEHOLDER:
        field, value = PLACEHOLDER[kind.value]
        assert getattr(element, field).value == value
        assert "placeholder" in element.body
    else:
        assert element.body == ""


def test_edit_without_an_editor_is_a_usage_error_and_writes_nothing(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EDITOR", raising=False)

    result = new(store, "component", "orders", "--edit")

    assert result.exit_code == ExitCode.USAGE
    assert "EDITOR" in result.stderr
    assert not (store / "components" / "orders.md").exists()


def test_edit_opens_the_written_file_in_the_editor(
    store: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called_with = tmp_path / "editor-arg"
    script = tmp_path / "fake-editor"
    script.write_text(f'#!/bin/sh\necho "$1" > "{called_with}"\n', encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("EDITOR", str(script))

    result = new(store, "component", "orders", "--edit")

    assert result.exit_code == ExitCode.OK
    written = store / "components" / "orders.md"
    assert written.is_file()
    assert called_with.read_text(encoding="utf-8").strip() == str(written)


def test_edit_and_print_together_is_a_usage_error(store: Path) -> None:
    """Editing a rendering bound for stdout would guess at what was meant."""
    result = new(store, "component", "orders", "--edit", "--print")

    assert result.exit_code == ExitCode.USAGE
    assert result.stdout == ""


def test_a_slug_that_breaks_the_id_pattern_is_a_usage_error(store: Path) -> None:
    result = new(store, "component", "Bad_Slug")

    assert result.exit_code == ExitCode.USAGE
    assert "Bad_Slug" in result.stderr
    assert not (store / "components").exists()


def test_new_without_a_usable_store_is_a_usage_error(tmp_path: Path) -> None:
    missing = new(tmp_path / "missing", "component", "orders")
    empty = tmp_path / "empty"
    empty.mkdir()
    systemless = new(empty, "component", "orders")

    assert missing.exit_code == ExitCode.USAGE
    assert "no store" in missing.stderr
    assert systemless.exit_code == ExitCode.USAGE
    assert "system.yaml" in systemless.stderr
    assert list(empty.iterdir()) == []


def test_a_marker_names_the_store_new_writes_into(tmp_path: Path) -> None:
    store = tmp_path / "design-store"
    marker = tmp_path / "repo" / ".absicht"
    marker.parent.mkdir()
    assert runner.invoke(app, ["--store", str(store), "init", "--name", "ACME"]).exit_code == (
        ExitCode.OK
    )
    marker.write_text(f"design: {store.resolve()}\n", encoding="utf-8")

    result = runner.invoke(app, ["--store", str(marker), "new", "component", "orders"])

    assert result.exit_code == ExitCode.OK
    assert (store / "components" / "orders.md").is_file()
    assert [path.name for path in marker.parent.iterdir()] == [".absicht"]


def test_json_output_names_the_id_and_the_path(store: Path) -> None:
    result = new(store, "component", "orders", "--json")

    assert result.exit_code == ExitCode.OK
    assert json.loads(result.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "id": "component:orders",
        "path": str(store / "components" / "orders.md"),
    }


def test_print_and_json_wrap_the_rendered_element(store: Path) -> None:
    result = new(store, "component", "orders", "--print", "--json")

    assert result.exit_code == ExitCode.OK
    assert json.loads(result.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "id": "component:orders",
        "element": dump_element(Component(id="component:orders", title="orders")),
    }


def test_json_is_accepted_on_either_side_of_the_command(store: Path) -> None:
    """`ab new --json`, not only `ab --json new`. See docs/adr/0001.

    This command's replacement for the whole-surface fold test in
    test_cli.py, which only works while a command has no body: parsing
    stdout as JSON is only possible if the fold in `options()` saw the flag
    the command declared under the name it expects.
    """
    ahead = runner.invoke(app, ["--json", "--store", str(store), "new", "component", "a"])
    behind = new(store, "component", "b", "--json")

    assert ahead.exit_code == ExitCode.OK
    assert behind.exit_code == ExitCode.OK
    assert json.loads(ahead.stdout)["id"] == "component:a"
    assert json.loads(behind.stdout)["id"] == "component:b"


def test_scaffolding_an_unknown_kind_names_the_culprit() -> None:
    """The library boundary, which the CLI's `Kind` enum never reaches."""
    with pytest.raises(NewError) as raised:
        scaffold("widget", "x")

    assert "widget" in str(raised.value)
