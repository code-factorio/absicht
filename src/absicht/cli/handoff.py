"""Step 3 — hand work to an agent.

The packet is the unit of output and the thing the whole project is a bet on.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from absicht.cli._app import app
from absicht.cli._common import (
    DEFAULT_FEATURES_DIR,
    DEFAULT_PACKET_DIR,
    PacketFormat,
    unimplemented,
)

PANEL = "Step 3 — hand work to an agent"
"""Where these commands appear in `ab --help`."""


@app.command(rich_help_panel=PANEL)
def packet(
    ctx: typer.Context,
    milestone: Annotated[str, typer.Argument(metavar="MILESTONE", help="The slice to assemble.")],
    out: Annotated[
        Path | None,
        typer.Option("--out", metavar="DIR", help=f"Default: {DEFAULT_PACKET_DIR}/<milestone>."),
    ] = None,
    to_stdout: Annotated[bool, typer.Option("--stdout")] = False,
    output_format: Annotated[
        PacketFormat,
        typer.Option("--format", help="json for programmatic consumers."),
    ] = PacketFormat.MD,
    horizon: Annotated[
        int,
        typer.Option("--horizon", metavar="N", help="Rings of contract-fidelity neighbours."),
    ] = 1,
    include: Annotated[
        list[str] | None,
        typer.Option("--include", metavar="REF", help="Force an element in; repeatable."),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", metavar="REF", help="Force an element out; repeatable."),
    ] = None,
    features: Annotated[
        bool,
        typer.Option(
            "--features/--no-features", help="Emit .feature files from behavioural criteria."
        ),
    ] = True,
    features_dir: Annotated[
        Path,
        typer.Option("--features-dir", metavar="DIR"),
    ] = DEFAULT_FEATURES_DIR,
    rev: Annotated[
        str | None,
        typer.Option("--rev", metavar="REF", help="Build from the store at a revision."),
    ] = None,
    seal: Annotated[
        bool,
        typer.Option("--seal", help="Write packet.lock so ab verify can run offline later."),
    ] = False,
) -> None:
    """Assemble the brief for one milestone.

    Milestone scope at full fidelity, one ring of neighbouring contracts, the
    decisions and NFRs that must hold, explicit freedoms, known unknowns, and the
    rejections that must not be re-proposed.
    """
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def features(
    ctx: typer.Context,
    milestone: Annotated[str, typer.Argument(metavar="MILESTONE")],
    out: Annotated[Path, typer.Option("--out", metavar="DIR")] = DEFAULT_FEATURES_DIR,
    to_stdout: Annotated[bool, typer.Option("--stdout")] = False,
    check_stale: Annotated[
        bool,
        typer.Option("--check", help="Fail if emitted output differs from what is on disk."),
    ] = False,
) -> None:
    """Render behavioural criteria to Gherkin, without the rest of the packet.

    Output is generated, never authored: an agent implements step definitions and
    may not touch these files.
    """
    unimplemented(ctx)
