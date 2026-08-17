"""``ab note``: the capture channel, as a command group of its own.

Notes are not elements, so this is deliberately not a ``Kind``: there is no
``ab new note`` and no ``ab list note`` (docs/tasks/50-addendum-conventions.md).
The verbs are capture's own — add, list, show, promote, drop — and the bodies
stay thin: resolve arguments, call ``absicht.notes``, render.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from datetime import date
from typing import Annotated

import typer

from absicht import notes
from absicht.cli._app import app
from absicht.cli._common import (
    JsonOption,
    Kind,
    ListFormat,
    effective_format,
    options,
)
from absicht.codec import dump_element
from absicht.findings import ExitCode
from absicht.load import StoreResolutionError, resolve_store
from absicht.models import SCHEMA_VERSION, Note

PANEL = "Step 1 — author and validate"
"""Where this group appears in `ab --help`: capture is authoring."""

note_app = typer.Typer(
    name="note",
    help="Capture thoughts against the store with near-zero friction.",
    no_args_is_help=True,
)
app.add_typer(note_app, rich_help_panel=PANEL)


@note_app.command("add")
def add(
    ctx: typer.Context,
    text: Annotated[
        str | None,
        typer.Argument(help="The note. Without TEXT: piped stdin, then --edit ($EDITOR)."),
    ] = None,
    ref: Annotated[
        str | None,
        typer.Option("--ref", metavar="REF", help="What it was captured against, when obvious."),
    ] = None,
    edit: Annotated[bool, typer.Option("--edit", help="Open $EDITOR on the written note.")] = False,
    json_output: JsonOption = False,
) -> None:
    """Capture a thought. The id is generated (note:a1b2c3), never asked for."""
    body = _body(text, edit)
    opts = options(ctx)
    try:
        written = notes.add(opts.store, body, created=date.today(), ref=ref, edit=edit)
        path = resolve_store(opts.store) / written.source
    except (notes.NoteError, StoreResolutionError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    if opts.json_output:
        typer.echo(
            json.dumps({"schema_version": SCHEMA_VERSION, "id": written.id, "path": str(path)})
        )
    else:
        typer.echo(f"wrote {written.id} to {path}")


def _body(text: str | None, edit: bool) -> str:
    """Where the note's body comes from: the argument, then a pipe, then --edit.

    A blank argument or pipe counts as absent — an empty capture is not a
    note — and with none of the three there is nothing to capture, which is a
    usage error rather than an empty file. Stdin is read only when it is not
    a tty, which is what keeps `--edit` from swallowing terminal input and a
    bare `ab note add` from blocking on one.
    """
    if text is None and not sys.stdin.isatty():
        text = sys.stdin.read()
    if text is not None and text.strip():
        return text
    if not edit:
        typer.echo("a note needs a body: pass TEXT, pipe it on stdin, or use --edit", err=True)
        raise typer.Exit(ExitCode.USAGE)
    return ""


@note_app.command("list")
def list_notes(
    ctx: typer.Context,
    ref: Annotated[str | None, typer.Option("--ref", metavar="REF")] = None,
    all_notes: Annotated[
        bool, typer.Option("--all", help="Include promoted notes, not just the inbox.")
    ] = False,
    output_format: Annotated[
        ListFormat,
        typer.Option("--format", help="ids for piping."),
    ] = ListFormat.TEXT,
    json_output: JsonOption = False,
) -> None:
    """The inbox: unpromoted notes, oldest first. Age is the pressure, not the count."""
    opts = options(ctx)
    try:
        selected = notes.select(opts.store, ref=ref, include_promoted=all_notes)
    except notes.NoteError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    today = date.today()
    output = effective_format(ctx, output_format, opts.json_output, json_member=ListFormat.JSON)
    if output is ListFormat.JSON:
        typer.echo(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "notes": [_entry(note, today) for note in selected],
                }
            )
        )
    elif output is ListFormat.IDS:
        # Silent on an empty answer, like every ids format: a lone blank line
        # would hand `xargs` one empty argument where no id is.
        if selected:
            typer.echo("\n".join(note.id for note in selected))
    else:
        typer.echo(_header(selected, today))
        for note in selected:
            typer.echo(_line(note, today))


def _header(selected: Sequence[Note], today: date) -> str:
    """`N notes, oldest X`: the count and the age of the oldest, nothing else."""
    if not selected:
        return "0 notes"
    count = len(selected)
    return f"{count} note{'s' if count != 1 else ''}, oldest {_age(selected[0].created, today)}"


def _line(note: Note, today: date) -> str:
    """One line per note: id, age, the anchor and the promotion when present, then the gist."""
    parts = [note.id, _age(note.created, today)]
    if note.ref is not None:
        parts.append(f"-> {note.ref}")
    if note.promoted_to is not None:
        parts.append(f"promoted to {note.promoted_to}")
    if gist := next((line.strip() for line in note.body.splitlines() if line.strip()), ""):
        parts.append(gist)
    return "  ".join(parts)


def _entry(note: Note, today: date) -> dict[str, object]:
    """The machine view of one entry: everything but the body — whose home is
    `show` — plus the exact age the header humanizes."""
    return {
        "id": note.id,
        "ref": note.ref,
        "created": note.created.isoformat(),
        "promoted_to": note.promoted_to,
        "age_days": (today - note.created).days,
    }


def _age(created: date, today: date) -> str:
    """A rough human age — the pressure reading, not accounting.

    Approximate buckets (30-day months, 365-day years) are the point: "3
    months" is the reading the addendum's own example wants, and a day-exact
    figure would bury it in precision nobody acts on differently.
    """
    days = (today - created).days
    if days <= 0:
        return "today"
    if days < 14:
        return _plural(days, "day")
    if days < 60:
        return _plural(days // 7, "week")
    if days < 365:
        return _plural(days // 30, "month")
    return _plural(days // 365, "year")


def _plural(count: int, unit: str) -> str:
    return f"{count} {unit}{'s' if count != 1 else ''}"


@note_app.command("show")
def show(
    ctx: typer.Context,
    note_id: Annotated[str, typer.Argument(help="The note to read.")],
    json_output: JsonOption = False,
) -> None:
    """One note, as authored: front matter and body."""
    opts = options(ctx)
    try:
        found = notes.get(opts.store, note_id)
    except notes.NoteError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    if opts.json_output:
        typer.echo(
            json.dumps({"schema_version": SCHEMA_VERSION, "note": found.model_dump(mode="json")})
        )
    else:
        typer.echo(dump_element(found))


@note_app.command("promote")
def promote(
    ctx: typer.Context,
    note_id: Annotated[str, typer.Argument(help="The note that became something.")],
    kind: Annotated[Kind, typer.Argument(help="The kind it became.")],
    slug: Annotated[
        str, typer.Argument(help="Its name within the kind; the id is generated from it.")
    ],
    json_output: JsonOption = False,
) -> None:
    """It became a question, decision, requirement or behavior: create the element, stamp the note."""
    opts = options(ctx)
    try:
        element = notes.promote(opts.store, note_id, kind.value, slug)
    except notes.NoteError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    if opts.json_output:
        typer.echo(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "note": note_id,
                    "promoted_to": element.id,
                }
            )
        )
    else:
        typer.echo(f"promoted {note_id} to {element.id}")


@note_app.command("drop")
def drop(
    ctx: typer.Context,
    note_id: Annotated[str, typer.Argument(help="The note that never mattered.")],
    json_output: JsonOption = False,
) -> None:
    """It never mattered; delete the file. A promoted note is refused."""
    opts = options(ctx)
    try:
        notes.drop(opts.store, note_id)
    except notes.NoteError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    if opts.json_output:
        typer.echo(json.dumps({"schema_version": SCHEMA_VERSION, "dropped": note_id}))
    else:
        typer.echo(f"dropped {note_id}")
