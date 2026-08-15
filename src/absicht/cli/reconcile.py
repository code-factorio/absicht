"""Step 4 — verify what came back.

Every other gate in a pipeline asks whether the code is well-formed. This group
asks whether it is the code that was asked for, which needs the design to answer.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from absicht.cli._app import app
from absicht.cli._common import (
    DEFAULT_DIFF_BASE,
    DocFormat,
    JsonOption,
    Kind,
    PlainFormat,
    ReportFormat,
    unimplemented,
)

PANEL = "Step 4 — verify what came back"
"""Where these commands appear in `ab --help`."""

marker_app = typer.Typer(
    name="marker",
    help=(
        "Manage .absicht discovery files in implementing repos. "
        "The store stays authoritative; markers are regenerable hints."
    ),
    no_args_is_help=True,
)
app.add_typer(marker_app, rich_help_panel=PANEL)


@app.command(rich_help_panel=PANEL)
def verify(
    ctx: typer.Context,
    packet: Annotated[
        Path | None,
        typer.Option(
            "--packet", metavar="PATH", help="Default: the sealed packet in the build dir."
        ),
    ] = None,
    repo: Annotated[
        list[Path] | None,
        typer.Option("--repo", metavar="PATH", help="Repeatable, for multi-repo slices."),
    ] = None,
    diff_base: Annotated[
        str,
        typer.Option("--diff-base", metavar="REF", help='What counts as "this change".'),
    ] = DEFAULT_DIFF_BASE,
    rule: Annotated[list[str] | None, typer.Option("--rule", metavar="ID")] = None,
    exclude_rule: Annotated[list[str] | None, typer.Option("--exclude-rule", metavar="ID")] = None,
    strict: Annotated[bool, typer.Option("--strict", help="Warnings become errors.")] = False,
    output_format: Annotated[ReportFormat, typer.Option("--format")] = ReportFormat.TEXT,
    report: Annotated[
        Path | None,
        typer.Option("--report", metavar="PATH", help="Write the reconciliation report."),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Check the change against the packet it was handed.

    That the diff touched only components in scope; that nothing marked
    `out_of_scope` was built; that nothing was built on an `unknown` without a
    recorded decision; that every seam in scope has a contract test that runs;
    that every `done_when` criterion has something verifying it; that scenario
    files are unmodified against the sealed digest; and that step definitions
    contain assertions.
    """
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def status(
    ctx: typer.Context,
    repo: Annotated[list[Path] | None, typer.Option("--repo", metavar="PATH")] = None,
    unit: Annotated[str | None, typer.Option("--unit", metavar="REF", help="One unit.")] = None,
    behind_only: Annotated[bool, typer.Option("--behind-only")] = False,
    since: Annotated[
        str | None,
        typer.Option(
            "--since", metavar="REF", help="Compare against a design rev, not watermarks."
        ),
    ] = None,
    fail_on_drift: Annotated[
        bool,
        typer.Option("--fail-on-drift", help="Non-zero when anything is behind. For CI."),
    ] = False,
    output_format: Annotated[PlainFormat, typer.Option("--format")] = PlainFormat.TEXT,
    json_output: JsonOption = False,
) -> None:
    """Where the code stands against the design.

    Computed from watermarks and implementation refs: units behind design head,
    which decisions and seam changes landed since each watermark, seams whose
    consumers have not caught up, components with no implementation reference,
    and milestones with unmet `done_when`.

    A watermark is a hint, not proof — it tends to over-claim, since a merge
    stamps it whether or not the work was finished.
    """
    unimplemented(ctx)


@app.command(rich_help_panel=PANEL)
def diff(
    ctx: typer.Context,
    ref_a: Annotated[str, typer.Argument(metavar="REF_A")],
    ref_b: Annotated[str, typer.Argument(metavar="REF_B")],
    scope: Annotated[
        str | None,
        typer.Option("--scope", metavar="REF", help="Limit to a subtree."),
    ] = None,
    kind: Annotated[Kind | None, typer.Option("--kind")] = None,
    output_format: Annotated[DocFormat, typer.Option("--format")] = DocFormat.TEXT,
    json_output: JsonOption = False,
) -> None:
    """What changed in the design between two revisions, as elements rather than lines.

    Decisions added, seams whose contract moved, requirements added or dropped,
    state transitions.
    """
    unimplemented(ctx)


@marker_app.command("sync")
def marker_sync(
    ctx: typer.Context,
    repo: Annotated[Path, typer.Option("--repo", metavar="PATH")],
    json_output: JsonOption = False,
) -> None:
    """Write or update a repo's marker from the store."""
    unimplemented(ctx)


@marker_app.command("check")
def marker_check(
    ctx: typer.Context,
    repo: Annotated[Path, typer.Option("--repo", metavar="PATH")],
    json_output: JsonOption = False,
) -> None:
    """Fail if a marker disagrees with the store."""
    unimplemented(ctx)


@marker_app.command("stamp")
def marker_stamp(
    ctx: typer.Context,
    repo: Annotated[Path, typer.Option("--repo", metavar="PATH")],
    unit: Annotated[str, typer.Option("--unit", metavar="REF")],
    milestone: Annotated[str, typer.Option("--milestone", metavar="REF")],
    json_output: JsonOption = False,
) -> None:
    """Move the watermark. Run from the commit that lands the work."""
    unimplemented(ctx)
