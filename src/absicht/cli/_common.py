"""Shared vocabulary for the ``ab`` command surface.

The value sets options choose from, the flags every command shares, and the
default store paths. Nothing here knows what a design store contains — this
module describes the *interface*, and the library behind it is free to change
shape without the surface moving.

``ExitCode`` and the severity grades are defined in ``absicht.findings`` — the
lowest layer both the surface and the report machinery may import — and only
imported here.

The option value sets are separate enums rather than one big ``Format`` because
Typer derives a command's choices from the annotation: sharing one enum would
offer ``sarif`` where only ``text`` and ``json`` exist, and the help text would
lie.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from absicht.findings import ExitCode

# --------------------------------------------------------------- store paths

DEFAULT_STORE = Path(".absicht")
STORE_ENVVAR = "ABSICHT_STORE"

BUILD_DIR = DEFAULT_STORE / "build"
DEFAULT_DESIGN_OUT = BUILD_DIR / "design.json"
DEFAULT_SITE_OUT = BUILD_DIR / "site"
DEFAULT_PACKET_DIR = BUILD_DIR / "packets"
DEFAULT_SCHEMA_OUT = Path("schema")
DEFAULT_FEATURES_DIR = Path("features")

DEFAULT_DIFF_BASE = "origin/HEAD"
"""What counts as "this change" when nothing says otherwise."""


# ------------------------------------------------------------- option values


class Kind(StrEnum):
    """The element kinds a store holds.

    `note` is deliberately absent: notes are not elements, so there is no
    `ab new note` and no `ab list note` — `ab note` is its own command group.
    The values are the `kind:` prefixes a ref carries, so a filter here is a
    prefix test and never a lookup.
    """

    TERM = "term"
    ACTOR = "actor"
    GOAL = "goal"
    REQ = "req"
    QUALITY = "quality"
    CONSTRAINT = "constraint"
    BEHAVIOR = "behavior"
    COMPONENT = "component"
    INTERFACE = "interface"
    DATA = "data"
    RESOURCE = "resource"
    LIBRARY = "library"
    EXTERNAL = "external"
    ASSUMPTION = "assumption"
    DECISION = "decision"
    QUESTION = "question"
    REJECTION = "rejection"
    MILESTONE = "milestone"


class Overlay(StrEnum):
    """Same diagram layout, different colouring."""

    STATE = "state"
    MILESTONE = "milestone"
    COVERAGE = "coverage"
    CHURN = "churn"


class PlainFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


class ReportFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    SARIF = "sarif"


class DocFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    MD = "md"


class ListFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    IDS = "ids"
    """One id per line, for piping."""


class TraceFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    MERMAID = "mermaid"


class DiagramFormat(StrEnum):
    SVG = "svg"
    MERMAID = "mermaid"
    D2 = "d2"


class PacketFormat(StrEnum):
    MD = "md"
    JSON = "json"


# ------------------------------------------------------------ global options


@dataclass(frozen=True, slots=True)
class GlobalOptions:
    """The flags every command shares, resolved once by the root callback.

    Commands read this instead of taking the same six parameters each, which is
    also what keeps them callable from a web or MCP surface later: the surface
    builds one of these, the command never touches ``sys.argv``.
    """

    store: Path = DEFAULT_STORE
    rev: str | None = None
    json_output: bool = False
    quiet: bool = False
    verbose: int = 0
    color: bool = True


JSON_HELP = "Machine output on stdout. Diagnostics stay on stderr."

JsonOption = Annotated[bool, typer.Option("--json", help=JSON_HELP)]
"""``--json`` again, on the command itself.

Click only accepts a group's options ahead of the subcommand, and `ab --json
check` is the wrong way round for the caller this flag exists for. Every command
declares this so `ab check --json` parses; `options` folds it into the global
one, so a body never has to look in two places. Declare it under exactly this
parameter name — that is the hook `options` reads. See docs/adr/0001.
"""


def options(ctx: typer.Context) -> GlobalOptions:
    """The resolved global flags for this invocation.

    ``--json`` is accepted on either side of the command name and means the same
    thing on both, so the two are or-ed rather than one shadowing the other.
    """
    resolved = ctx.find_object(GlobalOptions)
    if resolved is None:  # pragma: no cover - the root callback always sets it
        resolved = GlobalOptions()
    if ctx.params.get("json_output") and not resolved.json_output:
        return replace(resolved, json_output=True)
    return resolved


def color_enabled(no_color: bool) -> bool:
    """``--no-color``, ``NO_COLOR`` and a non-tty stdout all mean the same thing."""
    if no_color or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def effective_format[F: StrEnum](
    ctx: typer.Context, output_format: F, json_output: bool, *, json_member: F
) -> F:
    """``--json`` selects the ``json`` member of ``--format`` only while
    ``--format`` was left at its default; an explicitly passed ``--format``
    wins (docs/adr/0001 — closed, so every ``--format`` command shares this
    one spelling of it).

    The parameter source is compared by name rather than by importing
    ``click.core.ParameterSource``: click is typer's dependency, not ours, and
    the deps gate holds that line. The command's parameter must be named
    ``output_format``, which is what the source is looked up by.
    """
    source = ctx.get_parameter_source("output_format")
    if json_output and (source is None or source.name == "DEFAULT"):
        return json_member
    return output_format


def unimplemented(ctx: typer.Context) -> NoReturn:
    """Refuse a command that exists in the surface but has no body yet.

    The surface is signatures at this point: the flags, their types and their
    defaults are the contract, and the library behind them lands step by step.
    Exiting ``INTERNAL`` on stderr rather than raising keeps that honest for a
    caller — no traceback to parse, no output on stdout to mistake for a result.
    """
    typer.echo(f"{ctx.command_path}: not implemented yet", err=True)
    raise typer.Exit(ExitCode.INTERNAL)


def utc_now_iso() -> str:
    """A run-store timestamp: ISO-8601 UTC, read here at the CLI layer.

    The clock belongs to the surface, not the library — ``absicht.runstore``
    takes its timestamps as parameters for the same reason ``check`` takes
    ``today`` — and this is the one spelling of them, so the store's TEXT
    columns order lexicographically as timestamps.
    """
    return datetime.now(UTC).isoformat()
