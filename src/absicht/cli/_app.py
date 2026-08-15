"""The root command: the Typer app, the global flags, and the entry point.

Command modules import ``app`` from here and register themselves on it, so the
grouping in ``absicht.cli`` follows the delivery steps rather than one file
growing to hold everything.
"""

# Typer registers callbacks through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from absicht import __version__
from absicht.cli._common import (
    DEFAULT_STORE,
    STORE_ENVVAR,
    GlobalOptions,
    color_enabled,
)
from absicht.models import SCHEMA_VERSION

log = logging.getLogger(__name__)

app = typer.Typer(
    name="ab",
    help="Absicht — the design store. Holds what is true and what is permitted.",
    add_completion=False,
    pretty_exceptions_enable=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"absicht {__version__} (schema {SCHEMA_VERSION})")
        raise typer.Exit()


def _log_level(quiet: bool, verbose: int) -> int:
    """Diagnostics go to stderr, so the default is quiet enough to pipe stdout."""
    if quiet:
        return logging.ERROR
    return {0: logging.WARNING, 1: logging.INFO}.get(verbose, logging.DEBUG)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    store: Annotated[
        Path,
        typer.Option("--store", metavar="PATH", envvar=STORE_ENVVAR, help="Design store root."),
    ] = DEFAULT_STORE,
    rev: Annotated[
        str | None,
        typer.Option(
            "--rev",
            metavar="REF",
            help="Read the store at a git revision instead of the working tree.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Machine output on stdout. Diagnostics stay on stderr."),
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Errors only.")] = False,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Repeatable."),
    ] = 0,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Also implied by NO_COLOR and a non-tty stdout."),
    ] = False,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Print the version, including the schema version it speaks.",
        ),
    ] = False,
) -> None:
    ctx.obj = GlobalOptions(
        store=store,
        rev=rev,
        json_output=json_output,
        quiet=quiet,
        verbose=verbose,
        color=color_enabled(no_color),
    )
    logging.basicConfig(
        level=_log_level(quiet, verbose),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def main() -> None:
    app()
