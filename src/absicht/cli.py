"""The ``ab`` command. Typer adapter over the library.

This module is a shell and stays one. The rules that keep it that way, because
the web and MCP surfaces later depend on them:

- no business logic here — a command resolves arguments, calls the library and
  renders the result;
- no ``print`` outside the render layer, no ``sys.exit`` in the core;
  everything below returns values;
- ``--json`` on every command that produces output. Agents are the primary
  consumer of this tool and the terminal is the secondary one.

The command surface this grows into: ``check``, ``build``, ``packet``,
``status``, ``verify``. None of them exist yet — see the status table in the
README for the order they arrive in.
"""

# Typer registers callbacks through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import logging
from typing import Annotated

import typer

from absicht import __version__

log = logging.getLogger(__name__)

app = typer.Typer(
    name="ab",
    help="Absicht — the design store. Holds what is true and what is permitted.",
    add_completion=False,
    pretty_exceptions_enable=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"absicht {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
    _version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def main() -> None:
    app()
