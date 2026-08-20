"""``ab note`` and ``absicht.notes``: the capture channel, end to end.

Notes are defined by exclusion (addendum §6) — not elements, never packet
input — so these tests hold the exclusion as hard as the behavior: a store
with notes builds a design no element of which is a note, and the one check
rule that reads notes polices ``about`` and nothing else. The rest is the
group's contract: capture from an argument, a pipe or the editor; an inbox
ordered by age, because age is the pressure; promotion through the same
machinery ``ab new`` uses; and the two refusals that keep the record of what
a note became alive.
"""

from __future__ import annotations

import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from absicht import notes
from absicht.build import build as build_design
from absicht.build import design_json
from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.codec import dump_design, dump_element, parse_element
from absicht.models.design import (
    FORMAT_VERSION,
    Component,
    ComponentLevel,
    Design,
    Element,
    Note,
    Question,
    State,
)

runner = CliRunner()

ID_PATTERN = re.compile(r"^note:[0-9a-z]{6}$")
"""A note id: `note:` plus six lowercase base36 characters, never asked for."""


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """An initialized store: notes are captured against a store, not a directory."""
    root = tmp_path / "store"
    assert runner.invoke(app, ["--store", str(root), "init", "--name", "ACME"]).exit_code == (
        ExitCode.OK
    )
    return root


def note(store: Path, *argv: str) -> object:
    """`ab note` against `store`, with the common prefix elided."""
    return runner.invoke(app, ["--store", str(store), "note", *argv])


def _note_file(
    store: Path,
    note_id: str,
    *,
    created: date,
    body: str = "A thought.",
    ref: str | None = None,
    promoted_to: str | None = None,
) -> Path:
    """Hand-author one note file, the way a colleague's commit would deliver it."""
    path = store / "notes" / f"{note_id.removeprefix('note:')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        dump_element(
            Note(
                id=note_id,
                created_on=created,
                about=(ref,) if ref else (),
                promoted_to=promoted_to,
                text=body,
            )
        ),
        encoding="utf-8",
    )
    return path


def _parse(store: Path, note_id: str) -> Note:
    """Read one note back through the codec, as the loader would."""
    source = f"notes/{note_id.removeprefix('note:')}.md"
    parsed, _ = parse_element(
        (store / source).read_text(encoding="utf-8"), model=Note, source=source
    )
    return parsed


def _only_note_file(store: Path) -> Path:
    (only,) = (store / "notes").iterdir()
    return only


def _days_ago(days: int) -> date:
    return date.today() - timedelta(days=days)


def _clean_store(tmp_path: Path) -> Path:
    """A store that `ab check` has nothing to say about, for the rule tests.

    Hand-built rather than `init`-ed: every element is `specified` and owned,
    so the policy layer stays silent and a note finding is the only finding.
    """
    root = tmp_path / "clean"
    root.mkdir()
    (root / "design.yaml").write_text(
        dump_design(Design(id="design:acme", title="ACME", version="0.1.0")),
        encoding="utf-8",
    )
    root.joinpath("components").mkdir()
    (root / "components" / "cancellation.md").write_text(
        dump_element(
            Component(
                id="component:cancellation",
                title="Cancellation",
                state=State.SPECIFIED,
                owner="vinz",
                level=ComponentLevel.SYSTEM,
            )
        ),
        encoding="utf-8",
    )
    return root


# ------------------------------------------------------------------- capture


def test_add_with_a_text_argument_writes_a_parseable_note(store: Path) -> None:
    result = note(store, "add", "The packet scope grows unbounded", "--json")

    assert result.exit_code == ExitCode.OK
    written = _parse(store, json.loads(result.stdout)["id"])
    assert ID_PATTERN.match(written.id)
    assert written.created_on == date.today()
    assert written.about == ()
    assert written.promoted_to is None
    assert written.text == "The packet scope grows unbounded"
    # A note stores no `source`: its id already says where the file lives.
    assert (store / "notes" / f"{written.id.removeprefix('note:')}.md").is_file()


def test_add_reports_the_id_and_the_path_in_the_json_envelope(store: Path) -> None:
    result = note(store, "add", "A thought", "--json")

    assert result.exit_code == ExitCode.OK
    payload = json.loads(result.stdout)
    assert payload["format_version"] == FORMAT_VERSION
    assert ID_PATTERN.match(payload["id"])
    assert payload["path"] == str(store / "notes" / f"{payload['id'].removeprefix('note:')}.md")


def test_json_is_accepted_on_either_side_of_the_command(store: Path) -> None:
    """`ab note add --json`, not only `ab --json note add`. See docs/adr/0001."""
    ahead = runner.invoke(app, ["--json", "--store", str(store), "note", "add", "ahead"])
    behind = note(store, "add", "behind", "--json")

    assert ahead.exit_code == ExitCode.OK
    assert behind.exit_code == ExitCode.OK
    assert json.loads(ahead.stdout)["id"]
    assert json.loads(behind.stdout)["id"]


def test_add_reads_piped_stdin_when_no_argument_is_given(store: Path) -> None:
    result = runner.invoke(app, ["--store", str(store), "note", "add"], input="Piped thought")

    assert result.exit_code == ExitCode.OK
    path = _only_note_file(store)
    parsed, _ = parse_element(
        path.read_text(encoding="utf-8"), model=Note, source=f"notes/{path.name}"
    )
    assert parsed.text == "Piped thought"


def test_add_without_a_body_is_a_usage_error_and_writes_nothing(store: Path) -> None:
    """No argument, nothing on the pipe, no editor: nothing to capture."""

    result = runner.invoke(app, ["--store", str(store), "note", "add"])

    assert result.exit_code == ExitCode.USAGE
    assert "body" in result.stderr
    assert not (store / "notes").exists()


def test_add_with_edit_opens_the_editor_on_the_written_file(
    store: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called_with = tmp_path / "editor-arg"
    script = tmp_path / "fake-editor"
    script.write_text(f'#!/bin/sh\necho "$1" > "{called_with}"\n', encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("EDITOR", str(script))

    result = note(store, "add", "--edit")

    assert result.exit_code == ExitCode.OK
    written = _only_note_file(store)
    assert called_with.read_text(encoding="utf-8").strip() == str(written)
    # The file the editor was pointed at is a note the loader can read.
    assert parse_element(
        written.read_text(encoding="utf-8"), model=Note, source=f"notes/{written.name}"
    )


def test_add_refuses_a_ref_that_is_not_a_ref(store: Path) -> None:
    result = note(store, "add", "A thought", "--ref", "not a ref")

    assert result.exit_code == ExitCode.USAGE
    # `--ref` lands in `about`, the field that refuses it, and the message
    # names that field rather than the flag it arrived on.
    assert "about" in result.stderr
    assert not (store / "notes").exists()


def test_add_accepts_a_ref_that_does_not_resolve_yet(store: Path) -> None:
    """Capture first: an unresolvable anchor is the check layer's to report,
    never a reason to refuse the thought (addendum §6's friction rule)."""

    result = note(store, "add", "A thought", "--ref", "component:ghost", "--json")

    assert result.exit_code == ExitCode.OK
    assert _parse(store, json.loads(result.stdout)["id"]).about == ("component:ghost",)


def test_a_generated_id_redraws_rather_than_collides_with_a_note_in_the_store(
    store: Path,
) -> None:
    _note_file(store, "note:000000", created=date.today())

    drawn = notes.add(store, "Again", created=date.today(), rng=_ScriptedDraws([0, 1]))

    assert drawn.id == "note:000001"
    assert _parse(store, "note:000000").text == "A thought."
    assert _parse(store, "note:000001").text == "Again"


class _ScriptedDraws(random.Random):
    """A `Random` whose draws are scripted, so a test can watch a re-draw."""

    def __init__(self, values: list[int]) -> None:
        super().__init__(0)
        self._values = values

    def randrange(self, stop: int) -> int:
        return self._values.pop(0)


# --------------------------------------------------------------------- inbox


def test_list_orders_oldest_first_and_surfaces_the_age_of_the_oldest(store: Path) -> None:
    _note_file(store, "note:old001", created=_days_ago(90), body="The older thought")
    fresh = json.loads(note(store, "add", "The newer thought", "--json").stdout)["id"]

    result = note(store, "list")

    assert result.exit_code == ExitCode.OK
    lines = result.stdout.splitlines()
    assert lines[0] == "2 notes, oldest 3 months"
    assert lines[1].startswith("note:old001")
    assert "3 months" in lines[1]
    assert "The older thought" in lines[1]
    assert lines[2].startswith(fresh)
    assert "today" in lines[2]


def test_list_anchors_the_note_it_filters_on(store: Path) -> None:
    _note_file(
        store,
        "note:anchr1",
        created=_days_ago(3),
        ref="component:packet-builder",
        body="Anchored thought",
    )
    _note_file(store, "note:free01", created=_days_ago(3), body="Free thought")

    result = note(store, "list", "--ref", "component:packet-builder")
    nothing = note(store, "list", "--ref", "component:none")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines()[0] == "1 note, oldest 3 days"
    assert "note:anchr1" in result.stdout
    assert "-> component:packet-builder" in result.stdout
    assert "note:free01" not in result.stdout
    assert nothing.stdout == "0 notes\n"


def test_list_ids_and_json_are_the_machine_shapes(store: Path) -> None:
    _note_file(store, "note:old001", created=_days_ago(400))
    _note_file(store, "note:new001", created=_days_ago(1), ref="component:ghost")

    ids = note(store, "list", "--format", "ids")
    envelope = note(store, "list", "--json")

    assert ids.exit_code == ExitCode.OK
    assert ids.stdout == "note:old001\nnote:new001\n"
    payload = json.loads(envelope.stdout)
    assert payload["format_version"] == FORMAT_VERSION
    assert payload["notes"] == [
        {
            "id": "note:old001",
            "about": [],
            "created_on": _days_ago(400).isoformat(),
            "promoted_to": None,
            "age_days": 400,
        },
        {
            "id": "note:new001",
            "about": ["component:ghost"],
            "created_on": _days_ago(1).isoformat(),
            "promoted_to": None,
            "age_days": 1,
        },
    ]


def test_show_prints_the_note_as_authored(store: Path) -> None:
    note_id = json.loads(note(store, "add", "Look at the packet builder", "--json").stdout)["id"]

    shown = note(store, "show", note_id)
    enveloped = note(store, "show", note_id, "--json")

    assert shown.exit_code == ExitCode.OK
    assert shown.stdout == (store / "notes" / f"{note_id.removeprefix('note:')}.md").read_text(
        encoding="utf-8"
    ) + ("\n")
    payload = json.loads(enveloped.stdout)
    assert payload["format_version"] == FORMAT_VERSION
    assert payload["note"]["id"] == note_id
    assert payload["note"]["text"] == "Look at the packet builder"


# ------------------------------------------------------- the terminal states


def test_promote_creates_the_element_and_stamps_the_note(store: Path) -> None:
    note_id = json.loads(
        note(
            store, "add", "How long do we retain packets?", "--ref", "component:ghost", "--json"
        ).stdout
    )["id"]

    result = note(store, "promote", note_id, "question", "packet-retention")

    assert result.exit_code == ExitCode.OK
    element, _ = parse_element(
        (store / "questions" / "packet-retention.md").read_text(encoding="utf-8"),
        model=Question,
        source="questions/packet-retention.md",
    )
    assert element.id == "question:packet-retention"
    assert element.title == "packet-retention"  # the `ab new` default
    stamped = _parse(store, note_id)
    assert stamped.promoted_to == "question:packet-retention"
    assert stamped.text == "How long do we retain packets?"  # the note survives
    # Out of the inbox, in under --all
    assert note_id not in note(store, "list").stdout
    everything = note(store, "list", "--all")
    assert note_id in everything.stdout
    assert "promoted to question:packet-retention" in everything.stdout


def test_promote_json_names_both_sides(store: Path) -> None:
    note_id = json.loads(note(store, "add", "Why?", "--json").stdout)["id"]

    result = note(store, "promote", note_id, "question", "why", "--json")

    assert json.loads(result.stdout) == {
        "format_version": FORMAT_VERSION,
        "note": note_id,
        "promoted_to": "question:why",
    }


def test_promote_on_a_promoted_note_is_a_usage_error(store: Path) -> None:
    note_id = json.loads(note(store, "add", "Why?", "--json").stdout)["id"]
    assert note(store, "promote", note_id, "question", "why").exit_code == ExitCode.OK

    again = note(store, "promote", note_id, "decision", "why-not")

    assert again.exit_code == ExitCode.USAGE
    assert "already promoted" in again.stderr
    assert _parse(store, note_id).promoted_to == "question:why"


def test_drop_deletes_the_file(store: Path) -> None:
    note_id = json.loads(note(store, "add", "Never mattered", "--json").stdout)["id"]

    result = note(store, "drop", note_id)

    assert result.exit_code == ExitCode.OK
    assert not (store / "notes" / f"{note_id.removeprefix('note:')}.md").exists()
    assert note(store, "list").stdout == "0 notes\n"


def test_drop_on_a_promoted_note_is_a_usage_error(store: Path) -> None:
    """The record of what a note became must survive the inbox cleanup."""
    note_id = json.loads(note(store, "add", "Why?", "--json").stdout)["id"]
    assert note(store, "promote", note_id, "question", "why").exit_code == ExitCode.OK

    result = note(store, "drop", note_id)

    assert result.exit_code == ExitCode.USAGE
    assert "promoted" in result.stderr
    assert _parse(store, note_id).promoted_to == "question:why"


@pytest.mark.parametrize(
    ("verb", "argv"),
    [
        ("show", ["note:ghost1"]),
        ("promote", ["note:ghost1", "question", "x"]),
        ("drop", ["note:ghost1"]),
    ],
)
def test_an_unknown_note_id_is_a_usage_error(store: Path, verb: str, argv: list[str]) -> None:
    result = note(store, verb, *argv)

    assert result.exit_code == ExitCode.USAGE
    assert "no note" in result.stderr


# ----------------------------------------------------------------- exclusion


def test_a_store_with_notes_builds_a_design_no_element_of_which_is_a_note(store: Path) -> None:
    note_id = json.loads(note(store, "add", "How long?", "--json").stdout)["id"]
    assert note(store, "promote", note_id, "question", "retention").exit_code == ExitCode.OK
    _note_file(store, "note:loose01", created=_days_ago(2))

    design = build_design(store)
    artifact = json.loads(design_json(design))

    # Structural, not incidental: the exclusion is the point (addendum §6).
    assert not issubclass(Note, Element)
    assert [element.id for element in design.elements() if element.id.startswith("note:")] == []
    # Carried beside the graph, under a key of their own — and nowhere else,
    # so nothing that walks the design's elements can reach one.
    assert {entry["id"] for entry in artifact.pop("notes")} == {note_id, "note:loose01"}
    assert "note:" not in json.dumps(artifact)
    # The promotion target is in the graph; the note that became it is not.
    assert "question:retention" in {element.id for element in design.elements()}


# --------------------------------------------------------------- the one rule


def test_check_on_a_note_about_something_unresolvable_is_exactly_that_rule(
    tmp_path: Path,
) -> None:
    store = _clean_store(tmp_path)
    _note_file(store, "note:stuck1", created=_days_ago(5), ref="component:ghost")

    result = runner.invoke(
        app, ["--store", str(store), "check", "--severity", "info", "--format", "json"]
    )

    # `info` never moves the exit: a note about something not yet written is
    # the normal case, so this is reported and never failed on.
    assert result.exit_code == ExitCode.OK
    (only,) = json.loads(result.stdout)["findings"]
    assert only["rule_id"] == "policy/note-dangling"
    assert only["severity"] == "info"
    # Pinned whole: the finding names the note, the dead target, and nothing
    # vaguer — it is all an agent fixing the store gets to read.
    assert only["message"] == "note:stuck1 is about component:ghost, which nothing defines"
    assert only["ref"] == "note:stuck1"
    # A note keeps no `source`, so the finding has no file to point at.
    assert only["source"] is None


def test_check_on_a_note_whose_anchor_resolves_says_nothing(tmp_path: Path) -> None:
    store = _clean_store(tmp_path)
    _note_file(store, "note:done001", created=_days_ago(5), ref="component:cancellation")

    result = runner.invoke(app, ["--store", str(store), "check", "--severity", "info"])

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""


def test_check_explains_the_note_rule() -> None:
    result = runner.invoke(app, ["check", "--explain", "policy/note-dangling"])

    assert result.exit_code == ExitCode.OK
    assert "policy/note-dangling:" in result.stdout
