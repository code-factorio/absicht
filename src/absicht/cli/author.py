"""Step 1 — author and validate.

``ab check`` is the core of this group: everything downstream assumes it passed.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from absicht.cli._app import app
from absicht.cli._common import (
    DEFAULT_DIFF_BASE,
    DEFAULT_SCHEMA_OUT,
    JsonOption,
    Kind,
    ReportFormat,
    Severity,
    unimplemented,
)
from absicht.models import State

PANEL = "Step 1 — author and validate"
"""Where these commands appear in `ab --help`."""


@app.command(rich_help_panel=PANEL)
def init(
    ctx: typer.Context,
    name: Annotated[str | None, typer.Option("--name", metavar="NAME", help="System name.")] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Write into a non-empty directory."),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Scaffold a store."""
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def new(
    ctx: typer.Context,
    kind: Annotated[Kind, typer.Argument(help="What to create.")],
    slug: Annotated[str, typer.Argument(help="Name within the kind; the id is generated from it.")],
    title: Annotated[str | None, typer.Option("--title", metavar="TEXT")] = None,
    state: Annotated[State, typer.Option("--state")] = State.UNKNOWN,
    owner: Annotated[str | None, typer.Option("--owner", metavar="WHO")] = None,
    edit: Annotated[bool, typer.Option("--edit", help="Open $EDITOR.")] = False,
    to_stdout: Annotated[
        bool,
        typer.Option("--print", help="Write to stdout instead of the store."),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Create an element from a template, with a generated id."""
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def check(
    ctx: typer.Context,
    rule: Annotated[
        list[str] | None,
        typer.Option("--rule", "-r", metavar="ID", help="Only these rules; repeatable."),
    ] = None,
    exclude_rule: Annotated[
        list[str] | None,
        typer.Option("--exclude-rule", metavar="ID", help="Repeatable."),
    ] = None,
    severity: Annotated[
        Severity,
        typer.Option("--severity", help="Minimum severity reported."),
    ] = Severity.WARN,
    strict: Annotated[bool, typer.Option("--strict", help="Treat warnings as errors.")] = False,
    changed_only: Annotated[
        bool,
        typer.Option("--changed-only", help="Only elements touching the diff against --diff-base."),
    ] = False,
    diff_base: Annotated[str, typer.Option("--diff-base", metavar="REF")] = DEFAULT_DIFF_BASE,
    output_format: Annotated[
        ReportFormat,
        typer.Option("--format", help="sarif for code-scanning annotations."),
    ] = ReportFormat.TEXT,
    explain: Annotated[
        str | None,
        typer.Option(
            "--explain", metavar="ID", help="Print what a rule checks and why, then exit."
        ),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Validate the store: schema, integrity, policy.

    Schema is fields, types and patterns. Integrity is that every ref resolves,
    that `contains` and `depends_on` hold no cycles, and that criteria are
    anchored to their story. Policy is the judgement layer: an `unknown` needs an
    owner, a requirement needs a realizing component, a `one_way` decision needs
    a rationale body, an external's assumptions have not expired.
    """
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def schema(
    ctx: typer.Context,
    out: Annotated[Path, typer.Option("--out", metavar="DIR")] = DEFAULT_SCHEMA_OUT,
    check_stale: Annotated[
        bool,
        typer.Option("--check", help="Fail if the committed schema is stale."),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Emit JSON Schema for the file formats.

    Commit the output so editors give autocomplete and inline errors while
    authoring.
    """
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def migrate(
    ctx: typer.Context,
    to: Annotated[int | None, typer.Option("--to", metavar="N", help="Default: latest.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: JsonOption = False,
) -> None:
    """Migrate the store to a newer schema version."""
    unimplemented(ctx)
