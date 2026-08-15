"""Shared vocabulary for the ``ab`` command surface.

Exit codes, the value sets options choose from, the flags every command shares,
and the default store paths. Nothing here knows what a design store contains —
this module describes the *interface*, and the library behind it is free to
change shape without the surface moving.

The option value sets are separate enums rather than one big ``Format`` because
Typer derives a command's choices from the annotation: sharing one enum would
offer ``sarif`` where only ``text`` and ``json`` exist, and the help text would
lie.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

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


class ExitCode(IntEnum):
    """What the shell sees.

    ``FINDINGS`` versus ``USAGE`` is the distinction that matters: CI treats the
    first as a real result about the design and the second as a broken pipeline.
    ``USAGE`` is also what Click exits with on a bad flag, so the two agree
    without us having to intercept anything.
    """

    OK = 0
    """Success, or advisory findings only."""
    FINDINGS = 1
    """Findings at error severity — validation, verification, drift."""
    USAGE = 2
    """Usage error: bad flags, unknown ref, no store."""
    INTERNAL = 3
    """Internal error."""
    SCHEMA_MISMATCH = 4
    """Schema version mismatch; run ``ab migrate``."""


# ------------------------------------------------------------- option values


class Kind(StrEnum):
    """The element kinds a store holds."""

    COMPONENT = "component"
    SEAM = "seam"
    DATA = "data"
    REQUIREMENT = "requirement"
    NFR = "nfr"
    STORY = "story"
    DECISION = "decision"
    REJECTION = "rejection"
    QUESTION = "question"
    MILESTONE = "milestone"
    EXTERNAL = "external"


class Severity(StrEnum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


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


def unimplemented(ctx: typer.Context) -> NoReturn:
    """Refuse a command that exists in the surface but has no body yet.

    The surface is signatures at this point: the flags, their types and their
    defaults are the contract, and the library behind them lands step by step.
    Exiting ``INTERNAL`` on stderr rather than raising keeps that honest for a
    caller — no traceback to parse, no output on stdout to mistake for a result.
    """
    typer.echo(f"{ctx.command_path}: not implemented yet", err=True)
    raise typer.Exit(ExitCode.INTERNAL)
