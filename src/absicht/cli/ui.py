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

from absicht.build import BuildError
from absicht.cli._app import app
from absicht.cli._common import options
from absicht.findings import ExitCode
from absicht.git import GitError
from absicht.load import StoreResolutionError, resolve_store
from absicht.ui import DEFAULT_PORT, LOCALHOST, MissingExtraError, serve

PANEL = "The designer's interface"


@app.command(rich_help_panel=PANEL)
def ui(
    ctx: typer.Context,
    port: Annotated[int, typer.Option("--port", metavar="N")] = DEFAULT_PORT,
    host: Annotated[
        str,
        typer.Option("--host", metavar="ADDR", help="Bind address. Localhost by default."),
    ] = LOCALHOST,
) -> None:
    """Open the design in a browser: navigate it, and ask for changes."""
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
    try:
        serve(root, host=host, port=port, rev=opts.rev)
    except MissingExtraError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    except BuildError as exc:
        # A store that does not fold has nothing to show. Same verdict the
        # query commands give it.
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.FINDINGS) from exc
    except KeyboardInterrupt:  # pragma: no cover - the only way out of a server
        pass
