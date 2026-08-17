"""The ``ab`` command. Typer adapter over the library.

This package is a shell and stays one. The rules that keep it that way, because
the web and MCP surfaces later depend on them:

- no business logic here — a command resolves arguments, calls the library and
  renders the result;
- no ``print`` outside the render layer, no ``sys.exit`` in the core;
  everything below returns values;
- ``--json`` on every command that produces output. Agents are the primary
  consumer of this tool and the terminal is the secondary one.

The modules are the delivery steps from ``docs/spec/cli.md``, which is
also the order the bodies behind these signatures arrive in. A command
without a body yet is still a signature: the flags, their types and their
defaults are the contract, and calling one exits ``ExitCode.INTERNAL`` with
a note on stderr.
"""

from __future__ import annotations

from absicht.cli._app import app, main

# Importing a command module registers its commands, and registration order is
# the order the step panels appear in `ab --help`. Alphabetical would put step 3
# above step 2, so the sorter is off for this block.
# isort: off
from absicht.cli import author  # noqa: F401
from absicht.cli import note  # noqa: F401
from absicht.cli import query  # noqa: F401
from absicht.cli import handoff  # noqa: F401
from absicht.cli import reconcile  # noqa: F401

# isort: on

__all__ = ["app", "main"]
