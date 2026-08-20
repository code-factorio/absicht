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
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode, Kind
from absicht.codec import dump_element, parse_element
from absicht.load import load_store
from absicht.models.design import (
    FORMAT_VERSION,
    Behavior,
    Component,
    ComponentLevel,
    Resource,
    ResourceKind,
)
from absicht.new import NewError, scaffold
from absicht.resolve import Index, resolve

runner = CliRunner()

# The kinds whose model has required fields no default exists for, and the
# placeholders `ab new` fills them with: the enum's first declared member
# where an enum is involved, an obviously-replaceable string where the field
# is free text — each named again in a comment in the element's body.
PLACEHOLDER: dict[str, tuple[tuple[str, str], ...]] = {
    "term": (("definition", "replace me"),),
    "goal": (("outcome", "replace me"),),
    "req": (("statement", "replace me"),),
    "quality": (("attribute", "latency"),),
    "constraint": (("statement", "replace me"), ("constraint_kind", "regulatory")),
    "behavior": (("trigger", "replace me"),),
    "component": (("level", "system"),),
    "interface": (("style", "call"),),
    "resource": (("resource_kind", "store"), ("technology", "replace me")),
    "library": (("package", "replace me"), ("ecosystem", "replace me")),
    "assumption": (("statement", "replace me"),),
    "decision": (("choice", "replace me"),),
    "question": (("question", "replace me"),),
}

COMPONENT_BODY = (
    "<!-- level: system — placeholders `ab new` chose because the model has no "
    "defaults for them; replace them before this element is trusted. -->"
)
"""The body a scaffolded component carries: `Component.level` has no default,
so the template guesses the first `ComponentLevel` and owns up to it. Spelled
out here rather than imported, so the text is pinned and not mirrored."""


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
    assert sorted(path.name for path in store.iterdir()) == ["components", "design.yaml"]
    written = store / "components" / "cancellation-flow.md"
    assert [path.name for path in (store / "components").iterdir()] == ["cancellation-flow.md"]
    # A scaffold declares no relationships either: `relates` is the author's.
    assert parse_element(
        written.read_text(encoding="utf-8"),
        model=Component,
        source="components/cancellation-flow.md",
    ) == (
        Component(
            id="component:cancellation-flow",
            title="Cancellation flow",
            owner="vinz",
            level=ComponentLevel.SYSTEM,
            body=COMPONENT_BODY,
            source="components/cancellation-flow.md",
        ),
        (),
    )


def test_the_title_falls_back_to_the_slug_and_the_state_to_unknown(store: Path) -> None:
    """The two documented defaults: `--title` has none, `--state`'s is `unknown`."""
    result = new(store, "component", "orders")

    assert result.exit_code == ExitCode.OK
    element, _ = parse_element(
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
    assert result.stdout == (
        dump_element(
            Component(
                id="component:orders",
                title="orders",
                level=ComponentLevel.SYSTEM,
                body=COMPONENT_BODY,
            )
        )
        + "\n"
    )
    assert [path.name for path in store.iterdir()] == ["design.yaml"]


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
    drifted.write_text(
        "---\nid: component:orders\ntitle: Orders\nlevel: system\n---\n", encoding="utf-8"
    )

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
    element = Index(resolve(loaded)).local[f"{kind.value}:probe"]
    assert element.title == "Probe"
    placeholders = PLACEHOLDER.get(kind.value, ())
    for field, value in placeholders:
        # `str()` spells an enum member as its value, so the comparison is
        # the same one line for the enum placeholders and the free-text ones.
        assert str(getattr(element, field)) == value
        assert "placeholder" in element.body
    if not placeholders:
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


def test_an_editor_that_fails_is_reported_not_swallowed(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file is written either way; a silent non-edit is the failure."""
    monkeypatch.setenv("EDITOR", "false")

    result = new(store, "component", "orders", "--edit")

    assert result.exit_code == ExitCode.USAGE
    assert "exited with" in result.stderr
    assert (store / "components" / "orders.md").is_file()


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
    designless = new(empty, "component", "orders")

    assert missing.exit_code == ExitCode.USAGE
    assert "no store" in missing.stderr
    assert designless.exit_code == ExitCode.USAGE
    assert "design.yaml" in designless.stderr
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
        "format_version": FORMAT_VERSION,
        "id": "component:orders",
        "path": str(store / "components" / "orders.md"),
    }


def test_print_and_json_wrap_the_rendered_element(store: Path) -> None:
    result = new(store, "component", "orders", "--print", "--json")

    assert result.exit_code == ExitCode.OK
    assert json.loads(result.stdout) == {
        "format_version": FORMAT_VERSION,
        "id": "component:orders",
        "element": dump_element(
            Component(
                id="component:orders",
                title="orders",
                level=ComponentLevel.SYSTEM,
                body=COMPONENT_BODY,
            )
        ),
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


# --- the addendum's kinds --------------------------------------------------------


def test_new_resource_lands_in_resources_with_both_placeholders(store: Path) -> None:
    """A resource's two required fields have no defaults, so the template
    fills both and owns up to both: `store` is the first `ResourceKind`
    declared, and `replace me` is not a technology anybody would ship."""
    result = new(store, "resource", "session-cache")

    assert result.exit_code == ExitCode.OK
    assert [path.name for path in (store / "resources").iterdir()] == ["session-cache.md"]
    element, _ = parse_element(
        (store / "resources" / "session-cache.md").read_text(encoding="utf-8"),
        model=Resource,
        source="resources/session-cache.md",
    )
    assert element.resource_kind is ResourceKind.STORE
    assert element.technology == "replace me"
    assert "placeholder" in element.body


def test_new_behavior_carries_the_worked_observation_example(store: Path) -> None:
    """The behavior template is where an author first meets observations: the
    worked example from addendum §3.3, commented out in the body, anchored to
    THIS behavior's id so the `#obs-1` pattern is shown rather than described.
    Observation ids are authored inline, never generated — the file starts
    with zero observations, exactly as a behavior starts unobserved."""
    result = new(store, "behavior", "new-chat-session")

    assert result.exit_code == ExitCode.OK
    assert [path.name for path in (store / "behaviors").iterdir()] == ["new-chat-session.md"]
    element, _ = parse_element(
        (store / "behaviors" / "new-chat-session.md").read_text(encoding="utf-8"),
        model=Behavior,
        source="behaviors/new-chat-session.md",
    )
    assert element.trigger == "replace me"
    assert element.observations == ()
    assert "behavior:new-chat-session#obs-1" in element.body
    assert "outcome: must" in element.body
    assert "timing: immediate" in element.body


def test_the_scaffolded_kinds_are_what_ab_check_accepts(store: Path) -> None:
    """`ab check` accepts both templates once the author's part is assumed:
    an owner for each (`unknown` asks for one), and the observations the
    behavior template deliberately does not generate — the one finding a
    fresh behavior owes its authoring-not-being-done-yet, excluded here.
    The scaffolded `design.yaml` needs no completing by hand: a design is not
    an element, so it carries no state and nothing asks it for an owner."""
    assert new(store, "resource", "state-store", "--owner", "platform").exit_code == ExitCode.OK

    result = runner.invoke(app, ["--store", str(store), "check"])

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""

    assert new(store, "behavior", "emits", "--owner", "platform").exit_code == ExitCode.OK

    result = runner.invoke(
        app,
        ["--store", str(store), "check", "--exclude-rule", "policy/behavior-unobserved"],
    )

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""


@pytest.mark.parametrize("kind", ["resource", "behavior"])
def test_print_is_byte_stable_for_the_new_kinds(store: Path, kind: str) -> None:
    """Two `--print` runs agree, and agree with the file a write would have
    produced: the template is a function of the slug, nothing else."""
    first = new(store, kind, "probe", "--print")
    second = new(store, kind, "probe", "--print")

    assert first.exit_code == ExitCode.OK
    assert first.stdout == second.stdout
    assert new(store, kind, "probe").exit_code == ExitCode.OK
    assert first.stdout == ((store / f"{kind}s" / "probe.md").read_text(encoding="utf-8") + "\n")
