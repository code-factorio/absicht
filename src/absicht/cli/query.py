"""Step 2 — build, query, look at it.

``ab build`` folds the store into the one artifact everything downstream reads;
the rest of this group are projections of it.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from absicht.build import BuildError, design_json
from absicht.build import build as build_design
from absicht.cli._app import app
from absicht.cli._common import (
    DEFAULT_DESIGN_OUT,
    DEFAULT_SITE_OUT,
    DiagramFormat,
    DocFormat,
    GlobalOptions,
    JsonOption,
    Kind,
    ListFormat,
    Overlay,
    PlainFormat,
    TraceFormat,
    effective_format,
    options,
    unimplemented,
)
from absicht.findings import ExitCode
from absicht.git import GitError
from absicht.load import StoreResolutionError, resolve_store
from absicht.models import SCHEMA_VERSION, Confidence, Design, State
from absicht.render import UnknownRefError, neighbourhood

PANEL = "Step 2 — build, query, look at it"
"""Where these commands appear in `ab --help`."""


def _design(opts: GlobalOptions) -> Design:
    """The load → resolve path every command in this group shares.

    One spelling of the three ways a query invocation breaks: no store, or a
    `--rev` that does not resolve / a store outside any repository (git reads,
    not findings), are `USAGE`; a store whose files did not all load is
    `build`'s `FINDINGS`-level refusal — a partial artifact is not an answer
    to a query either (docs/tasks/21-show.md's reuse rule).
    """
    try:
        root = resolve_store(opts.store)
        return build_design(root, rev=opts.rev)
    except (StoreResolutionError, GitError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    except BuildError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.FINDINGS) from exc


@app.command(rich_help_panel=PANEL)
def build(
    ctx: typer.Context,
    out: Annotated[Path, typer.Option("--out", metavar="PATH")] = DEFAULT_DESIGN_OUT,
    to_stdout: Annotated[bool, typer.Option("--stdout")] = False,
    check_stale: Annotated[
        bool,
        typer.Option("--check", help="Diff against the existing artifact; non-zero if it moved."),
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Fold the store into one normalized JSON document.

    Deterministic — same input, byte-identical output. Everything downstream
    reads this and nothing else.
    """
    opts = options(ctx)
    design = _design(opts)
    text = design_json(design)
    if to_stdout:
        # `nl=False`: the document ends in the newline a file gets, so stdout
        # is byte-identical to what a write would have produced.
        typer.echo(text, nl=False)
    if check_stale:
        _check_artifact(out, text, json_output=opts.json_output, verdict_stderr=to_stdout)
        return
    if to_stdout:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    if opts.json_output:
        typer.echo(json.dumps({"schema_version": SCHEMA_VERSION, "out": str(out)}))
    else:
        typer.echo(f"wrote {out}")


def _check_artifact(out: Path, text: str, *, json_output: bool, verdict_stderr: bool) -> None:
    """Compare a fresh build against the artifact at ``out``, never writing it.

    Raw bytes, not text, so a corrupted artifact is a drift finding rather
    than a decode crash. A missing artifact counts as moved: the drift gate
    exists to catch the artifact being wrong, and absent is wrong. When
    ``--stdout`` occupies stdout with the artifact itself, the verdict moves
    to stderr — diagnostics never mix into the machine output.
    """
    fresh = out.is_file() and out.read_bytes() == text.encode("utf-8")
    if json_output:
        typer.echo(
            json.dumps({"schema_version": SCHEMA_VERSION, "out": str(out), "stale": not fresh}),
            err=verdict_stderr,
        )
    elif fresh:
        typer.echo(f"{out} is up to date", err=verdict_stderr)
    else:
        state = "differs from a fresh build" if out.is_file() else "does not exist yet"
        typer.echo(f"stale: {out} {state}", err=verdict_stderr)
        typer.echo(f"run ab build --out {out} to refresh", err=verdict_stderr)
    if not fresh:
        raise typer.Exit(ExitCode.FINDINGS)


@app.command(rich_help_panel=PANEL)
def show(
    ctx: typer.Context,
    ref: Annotated[str, typer.Argument(metavar="REF", help="The element to resolve.")],
    output_format: Annotated[DocFormat, typer.Option("--format")] = DocFormat.TEXT,
    depth: Annotated[
        int,
        typer.Option(
            "--depth",
            metavar="N",
            help="How far to follow the element's own refs; the inbound side stays one hop.",
        ),
    ] = 1,
    body: Annotated[bool, typer.Option("--body/--no-body", help="Include the prose body.")] = True,
    json_output: JsonOption = False,
) -> None:
    """One element, resolved: its own fields, what points at it, what it points at."""
    opts = options(ctx)
    if depth < 0:
        typer.echo("--depth counts hops out from REF; it cannot be negative", err=True)
        raise typer.Exit(ExitCode.USAGE)
    design = _design(opts)
    try:
        view = neighbourhood(design, ref, depth=depth)
    except UnknownRefError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    output = effective_format(ctx, output_format, opts.json_output, json_member=DocFormat.JSON)
    if output is DocFormat.JSON:
        typer.echo(json.dumps(view.render_json(include_body=body)))
    elif output is DocFormat.MD:
        typer.echo(view.render_markdown(include_body=body))
    else:
        typer.echo(view.render_text(include_body=body))


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
    json_output: JsonOption = False,
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
    json_output: JsonOption = False,
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
    json_output: JsonOption = False,
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
    json_output: JsonOption = False,
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
    json_output: JsonOption = False,
) -> None:
    """Manage diagram positions.

    Positions are design data, not a rendering detail. Stable layout is what
    makes the diagrams worth having — if boxes move on every build, spatial
    memory never forms.
    """
    unimplemented(ctx)
