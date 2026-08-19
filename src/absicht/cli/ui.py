"""The designer's interface.

One command, and it is a launcher: resolve the store, hand it to
:mod:`absicht.ui`, and stay out of the way. The rules in
:mod:`absicht.cli` hold here too — no design logic in this file.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from typing import Annotated

import typer

from absicht.cli._app import app
from absicht.cli._common import options
from absicht.findings import ExitCode
from absicht.git import GitError
from absicht.load import StoreResolutionError, resolve_store

PANEL = "The designer's interface"

DEFAULT_HOST = "127.0.0.1"
"""A design store is not something to publish."""

DEFAULT_PORT = 8765


@app.command(rich_help_panel=PANEL)
def ui(
    ctx: typer.Context,
    port: Annotated[int, typer.Option("--port", metavar="N")] = DEFAULT_PORT,
    host: Annotated[
        str,
        typer.Option("--host", metavar="ADDR", help="Bind address. Localhost by default."),
    ] = DEFAULT_HOST,
) -> None:
    """Open the design in a browser: navigate it, and ask for changes."""
    # Imported here, not at module scope: fastapi and uvicorn are the `ui`
    # extra, and `ab --help` must work without them.
    from absicht.ui import serve

    opts = options(ctx)
    if not 1 <= port <= 65535:
        typer.echo("--port must be between 1 and 65535", err=True)
        raise typer.Exit(ExitCode.USAGE)
    try:
        root = resolve_store(opts.store)
    except (StoreResolutionError, GitError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc

    typer.echo(f"absicht on http://{host}:{port} (Ctrl-C to stop)", err=True)
    serve(root, host=host, port=port, rev=opts.rev)
