"""Step 1 — author and validate.

``ab check`` is the core of this group: everything downstream assumes it passed.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
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
    options,
    unimplemented,
)
from absicht.codec import dump_element
from absicht.findings import ExitCode, Severity
from absicht.init import InitError, init_embedded, init_reference
from absicht.migrate import MigrationError, migrate_store
from absicht.models import SCHEMA_VERSION, State
from absicht.new import NewError, create, scaffold
from absicht.schema import stale_schemas, write_schemas

PANEL = "Step 1 — author and validate"
"""Where these commands appear in `ab --help`."""


@app.command(rich_help_panel=PANEL)
def init(
    ctx: typer.Context,
    embedded: Annotated[
        bool,
        typer.Option("--embedded", help="Store as .absicht/ in this repo. The default mode."),
    ] = False,
    reference: Annotated[
        str | None,
        typer.Option(
            "--reference",
            metavar="URL",
            help="Write an .absicht file pointing at the store at URL.",
        ),
    ] = None,
    name: Annotated[str | None, typer.Option("--name", metavar="NAME", help="System name.")] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Write into an existing .absicht/ that has no elements yet."),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Scaffold a store."""
    if embedded and reference is not None:
        typer.echo("choose one mode: --embedded and --reference are mutually exclusive", err=True)
        raise typer.Exit(ExitCode.USAGE)
    opts = options(ctx)
    try:
        result = (
            init_reference(opts.store, reference)
            if reference is not None
            else init_embedded(opts.store, name, force=force)
        )
    except InitError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    if opts.json_output:
        typer.echo(
            json.dumps(
                {"schema_version": SCHEMA_VERSION, "mode": result.mode, "path": str(result.path)}
            )
        )
    elif result.mode == "reference":
        typer.echo(f"wrote reference marker {result.path} pointing at {reference}")
    else:
        typer.echo(f"initialized embedded store at {result.path}")


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
    if edit and to_stdout:
        typer.echo(
            "--edit opens $EDITOR on the file it writes; there is no file with --print",
            err=True,
        )
        raise typer.Exit(ExitCode.USAGE)
    opts = options(ctx)
    try:
        element = scaffold(kind.value, slug, title=title, state=state, owner=owner)
        if not to_stdout:
            path = create(opts.store, element, edit=edit)
    except NewError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    if to_stdout:
        if opts.json_output:
            typer.echo(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "id": element.id,
                        "element": dump_element(element),
                    }
                )
            )
        else:
            typer.echo(dump_element(element))
    elif opts.json_output:
        typer.echo(
            json.dumps({"schema_version": SCHEMA_VERSION, "id": element.id, "path": str(path)})
        )
    else:
        typer.echo(f"wrote {element.id} to {path}")


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
    opts = options(ctx)
    # `--check` compares against `--out` rather than always the committed
    # `schema/`: one flag, one meaning. The pairing is odd only because the
    # committed copy is the default — a CI job or a fork checking a copy
    # elsewhere names the same directory it would regenerate into.
    if check_stale:
        stale = stale_schemas(out)
        if opts.json_output:
            typer.echo(
                json.dumps(
                    {"schema_version": SCHEMA_VERSION, "out": str(out), "stale": list(stale)}
                )
            )
        elif stale:
            for name in stale:
                typer.echo(f"stale: {name}")
            typer.echo(f"run ab schema --out {out} to refresh")
        else:
            typer.echo(f"{out} is up to date")
        if stale:
            raise typer.Exit(ExitCode.FINDINGS)
        return
    written = write_schemas(out)
    if opts.json_output:
        typer.echo(
            json.dumps({"schema_version": SCHEMA_VERSION, "out": str(out), "wrote": list(written)})
        )
    else:
        typer.echo(f"wrote {len(written)} schema files to {out}")


@app.command(rich_help_panel=PANEL)
def migrate(
    ctx: typer.Context,
    to: Annotated[int | None, typer.Option("--to", metavar="N", help="Default: latest.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: JsonOption = False,
) -> None:
    """Migrate the store to a newer schema version.

    There is no newer version yet, so today this is the seam: a store at the
    running version is already current, and a target the registry cannot
    reach is a usage error naming where the walk got stuck.
    """
    opts = options(ctx)
    # `--dry-run` changes nothing while the registry is empty — there is no
    # migration to run, so there is nothing to hold back either. It stays on
    # the surface so the applier that lands with version 2 has its switch
    # already at the call site.
    try:
        result = migrate_store(opts.store, to=to)
    except MigrationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    except NotImplementedError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.INTERNAL) from exc
    if opts.json_output:
        typer.echo(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "from": result.from_version,
                    "to": result.to_version,
                }
            )
        )
    else:
        typer.echo(f"already current at schema version {result.to_version}")
