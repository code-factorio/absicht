"""Step 2 — build, query, look at it.

``ab build`` folds the store into the one artifact everything downstream reads;
the rest of this group are projections of it.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from absicht.cli._app import app
from absicht.cli._common import (
    DEFAULT_DESIGN_OUT,
    DEFAULT_SITE_OUT,
    DiagramFormat,
    DocFormat,
    Kind,
    ListFormat,
    Overlay,
    PlainFormat,
    TraceFormat,
    unimplemented,
)
from absicht.models import Confidence, State

PANEL = "Step 2 — build, query, look at it"
"""Where these commands appear in `ab --help`."""


@app.command(rich_help_panel=PANEL)
def build(
    ctx: typer.Context,
    out: Annotated[Path, typer.Option("--out", metavar="PATH")] = DEFAULT_DESIGN_OUT,
    to_stdout: Annotated[bool, typer.Option("--stdout")] = False,
    check_stale: Annotated[
        bool,
        typer.Option("--check", help="Diff against the existing artifact; non-zero if it moved."),
    ] = False,
) -> None:
    """Fold the store into one normalized JSON document.

    Deterministic — same input, byte-identical output. Everything downstream
    reads this and nothing else.
    """
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def show(
    ctx: typer.Context,
    ref: Annotated[str, typer.Argument(metavar="REF", help="The element to resolve.")],
    output_format: Annotated[DocFormat, typer.Option("--format")] = DocFormat.TEXT,
    depth: Annotated[
        int,
        typer.Option("--depth", metavar="N", help="How far to follow refs."),
    ] = 1,
    body: Annotated[bool, typer.Option("--body/--no-body", help="Include the prose body.")] = True,
) -> None:
    """One element, resolved: its own fields, what points at it, what it points at."""
    unimplemented(ctx)


@app.command("list", rich_help_panel=PANEL)
def list_elements(
    ctx: typer.Context,
    kind: Annotated[Kind, typer.Argument(help="Which kind to list.")],
    state: Annotated[list[State] | None, typer.Option("--state", help="Repeatable.")] = None,
    confidence: Annotated[Confidence | None, typer.Option("--confidence", metavar="LEVEL")] = None,
    owner: Annotated[str | None, typer.Option("--owner", metavar="WHO")] = None,
    unowned: Annotated[bool, typer.Option("--unowned")] = False,
    tag: Annotated[
        list[str] | None, typer.Option("--tag", metavar="TAG", help="Repeatable.")
    ] = None,
    milestone: Annotated[
        str | None,
        typer.Option("--milestone", metavar="REF", help="Members of a milestone's scope."),
    ] = None,
    orphaned: Annotated[bool, typer.Option("--orphaned", help="Nothing refers to it.")] = False,
    output_format: Annotated[
        ListFormat,
        typer.Option("--format", help="ids for piping."),
    ] = ListFormat.TEXT,
) -> None:
    """List elements of one kind, filtered."""
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def gaps(
    ctx: typer.Context,
    kind: Annotated[Kind | None, typer.Option("--kind")] = None,
    owner: Annotated[str | None, typer.Option("--owner", metavar="WHO")] = None,
    overdue: Annotated[bool, typer.Option("--overdue")] = False,
    blocking: Annotated[
        str | None,
        typer.Option("--blocking", metavar="REF", help="Only gaps blocking this element."),
    ] = None,
    output_format: Annotated[PlainFormat, typer.Option("--format")] = PlainFormat.TEXT,
) -> None:
    """Everything unfinished, as a worklist.

    `unknown`, `observed` and `delegated` elements, open questions, unowned
    elements, and expired external assumptions.
    """
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def trace(
    ctx: typer.Context,
    ref: Annotated[str, typer.Argument(metavar="REF", help="Where to start.")],
    to: Annotated[
        str | None,
        typer.Option("--to", metavar="REF", help="Paths between two elements."),
    ] = None,
    up: Annotated[bool, typer.Option("--up", help="Default: both directions.")] = False,
    down: Annotated[bool, typer.Option("--down", help="Default: both directions.")] = False,
    output_format: Annotated[TraceFormat, typer.Option("--format")] = TraceFormat.TEXT,
) -> None:
    """Traceability paths through the graph.

    Requirement to component to seam to decision, in either direction.
    """
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def render(
    ctx: typer.Context,
    out: Annotated[Path, typer.Option("--out", metavar="DIR")] = DEFAULT_SITE_OUT,
    serve: Annotated[
        bool,
        typer.Option("--serve", help="Local preview with rebuild on change."),
    ] = False,
    port: Annotated[int, typer.Option("--port", metavar="N")] = 8000,
    overlay: Annotated[
        list[Overlay] | None,
        typer.Option("--overlay", help="Repeatable; same layout, different colouring."),
    ] = None,
    output_format: Annotated[
        DiagramFormat,
        typer.Option("--format", help="Diagram output."),
    ] = DiagramFormat.SVG,
    scope: Annotated[
        str | None,
        typer.Option("--scope", metavar="REF", help="Render one subtree."),
    ] = None,
) -> None:
    """Generate the read-only site: element pages, traceability, gaps, diagrams."""
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def layout(
    ctx: typer.Context,
    recompute: Annotated[
        bool,
        typer.Option("--recompute", help="Re-run the deterministic layout for new elements only."),
    ] = False,
    recompute_all: Annotated[
        bool,
        typer.Option("--recompute-all", help="Throw away pinned positions."),
    ] = False,
    seed: Annotated[int, typer.Option("--seed", metavar="N")] = 0,
    check_positions: Annotated[
        bool,
        typer.Option("--check", help="Fail if any element has no position."),
    ] = False,
) -> None:
    """Manage diagram positions.

    Positions are design data, not a rendering detail. Stable layout is what
    makes the diagrams worth having — if boxes move on every build, spatial
    memory never forms.
    """
    unimplemented(ctx)
