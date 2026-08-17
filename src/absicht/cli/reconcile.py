"""Step 4 — verify what came back.

Every other gate in a pipeline asks whether the code is well-formed. This group
asks whether it is the code that was asked for, which needs the design to answer.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from absicht.build import BuildError
from absicht.build import build as build_design
from absicht.cli._app import app
from absicht.cli._common import (
    DEFAULT_DIFF_BASE,
    DEFAULT_PACKET_DIR,
    DocFormat,
    GlobalOptions,
    JsonOption,
    Kind,
    PlainFormat,
    ReportFormat,
    effective_format,
    options,
    utc_now_iso,
)
from absicht.cli.query import _design
from absicht.diff import diff as diff_store
from absicht.findings import ExitCode, Report
from absicht.git import GitError, current_rev
from absicht.load import StoreMode, StoreResolutionError, locate_store, resolve_store
from absicht.markers import MarkerError
from absicht.markers import check as check_marker
from absicht.markers import stamp as stamp_marker
from absicht.markers import sync as sync_marker
from absicht.models import SCHEMA_VERSION, Packet, PacketLock
from absicht.render import UnknownRefError
from absicht.runstore import RunStoreError, packet_id, record_run
from absicht.status import StatusUsageError
from absicht.status import status as status_report
from absicht.verify import (
    ObservationSummary,
    VerifyContext,
    VerifyUsageError,
    context_for,
    criterion_results,
    discover_sealed_packet,
    load_sealed_packet,
    observation_summary,
    run_rules,
    summary_json,
    summary_lines,
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
    opts = options(ctx)
    try:
        # The one sealed packet in the build dir, or the one --packet names:
        # zero or several candidates is a guess verify refuses to make.
        path = packet if packet is not None else discover_sealed_packet(DEFAULT_PACKET_DIR)
        brief, lock = load_sealed_packet(path)
        context = context_for(
            brief, lock, diff_base=diff_base, repos=tuple(repo) if repo else (Path(),)
        )
        result = run_rules(
            context,
            include=frozenset(rule) if rule is not None else None,
            exclude=frozenset(exclude_rule or ()),
        )
    except VerifyUsageError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    _record_run(opts, brief, lock, context)
    summary = observation_summary(context)
    body = _report_body(
        result,
        effective_format(ctx, output_format, opts.json_output, json_member=ReportFormat.JSON),
        summary,
    )
    if body:
        typer.echo(body)
    if report is not None:
        # In addition to stdout, never instead of it: --report says "write",
        # and the format flags already govern what goes to stdout.
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text((body + "\n") if body else "", encoding="utf-8")
    raise typer.Exit(result.exit_code(strict=strict))


def _record_run(
    opts: GlobalOptions, packet: Packet, lock: PacketLock, context: VerifyContext
) -> None:
    """One verification run into the run store — addendum §8's second tuple.

    Recorded whatever the verdict: a run with findings is still a run, which
    is the whole point of keeping history. The packet id is the digest's, so
    the run lands beside its issuance; the commit is the first `--repo`'s
    HEAD — the code under verification, one spelling of it for a multi-repo
    slice. Verification itself stays offline: when no design store can be
    located beside it the run simply leaves no history, said on stderr
    rather than swallowed. A store this ab cannot safely write fails the
    command by name before any report is printed — history quietly lost is
    the failure mode §8 exists to prevent."""
    try:
        root = resolve_store(opts.store)
    except StoreResolutionError as exc:
        typer.echo(f"verification run not recorded: {exc}", err=True)
        return
    try:
        record_run(
            root,
            packet_id=packet_id(packet.milestone, lock.design_rev),
            commit_sha=current_rev(context.repos[0]),
            recorded_at=utc_now_iso(),
            results=criterion_results(context),
        )
    except RunStoreError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.SCHEMA_MISMATCH) from exc
    except GitError as exc:
        typer.echo(f"cannot record the verification run: {exc}", err=True)
        raise typer.Exit(ExitCode.USAGE) from exc


def _report_body(result: Report, output_format: ReportFormat, summary: ObservationSummary) -> str:
    """The report as one string in the asked-for shape — what stdout shows and
    `--report` writes, so the two cannot drift. An empty text report is the
    empty string: silence is the pass signal a human greps for, the spelling
    `ab check` already uses. The observation summary rides along in text and
    json — advisory results are visibility, never findings, so it cannot touch
    the exit code — and has no SARIF spelling: a note with nowhere to land is
    not an annotation."""
    if output_format is ReportFormat.JSON:
        return json.dumps({**result.render_json(), "summary": summary_json(summary)})
    if output_format is ReportFormat.SARIF:
        return json.dumps(result.render_sarif())
    return "\n".join(line for line in (result.render_text(), *summary_lines(summary)) if line)


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
    opts = options(ctx)
    try:
        # locate_store rather than _design's resolve_store: which mode the
        # store was reached in is the report's whole shape, and only the
        # locating walk knows it.
        located = locate_store(opts.store)
        design = build_design(located.root, rev=opts.rev)
    except (StoreResolutionError, GitError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    except BuildError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.FINDINGS) from exc
    try:
        report = status_report(
            design,
            located,
            repos=tuple(repo) if repo else (),
            unit=unit,
            since=since,
            behind_only=behind_only,
        )
    except (StatusUsageError, MarkerError, GitError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    output = effective_format(ctx, output_format, opts.json_output, json_member=PlainFormat.JSON)
    body = json.dumps(report.render_json()) if output is PlainFormat.JSON else report.render_text()
    if body:
        # Empty stays silent, like `list`, `gaps` and `trace`: no blank line
        # where a fact would be.
        typer.echo(body)
    if located.mode is StoreMode.EMBEDDED:
        _note_reference_only(repo, since, behind_only, fail_on_drift)
    if fail_on_drift and report.drift:
        raise typer.Exit(ExitCode.FINDINGS)


def _note_reference_only(
    repo: list[Path] | None, since: str | None, behind_only: bool, fail_on_drift: bool
) -> None:
    """Say, rather than silently ignore, the flags that mean something only in
    reference mode: embedded, design and code land in the same commit and
    nothing can be behind (docs/tasks/42-status.md asks for exactly that
    honesty). stderr, so the machine output stays clean."""
    passed = [
        *(["--repo"] if repo else []),
        *(["--since"] if since is not None else []),
        *(["--behind-only"] if behind_only else []),
        *(["--fail-on-drift"] if fail_on_drift else []),
    ]
    if passed:
        verb = "is" if len(passed) == 1 else "are"
        typer.echo(
            f"embedded mode: {', '.join(passed)} {verb} reference-mode only — "
            "design and code land in the same commit, nothing can be behind",
            err=True,
        )


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
    opts = options(ctx)
    try:
        result = diff_store(
            resolve_store(opts.store),
            ref_a,
            ref_b,
            scope=scope,
            # The CLI's `Kind` enum value, not the enum: `absicht.diff` sits
            # below this layer and names kinds the way `Index.orphaned` does.
            kind=None if kind is None else kind.value,
        )
    except (StoreResolutionError, GitError, UnknownRefError, ValueError) as exc:
        # No store, a rev that does not resolve, an unknown `--scope` ref:
        # all broken invocations.
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    except BuildError as exc:
        # A store that does not load cleanly at either revision is `build`'s
        # FINDINGS-level refusal — a partial diff is not an answer either.
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.FINDINGS) from exc
    output = effective_format(ctx, output_format, opts.json_output, json_member=DocFormat.JSON)
    if output is DocFormat.JSON:
        typer.echo(json.dumps(result.render_json()))
        return
    body = result.render_markdown() if output is DocFormat.MD else result.render_text()
    # Empty stays silent, like `list`, `gaps` and `trace`: no blank line where
    # a change would be.
    if body:
        typer.echo(body)


@marker_app.command("sync")
def marker_sync(
    ctx: typer.Context,
    repo: Annotated[Path, typer.Option("--repo", metavar="PATH")],
    json_output: JsonOption = False,
) -> None:
    """Write or update a repo's marker from the store."""
    opts = options(ctx)
    root, design = _design(opts)
    try:
        marker = sync_marker(design, repo, design_url=_design_url(root, repo))
    except MarkerError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    if opts.json_output:
        typer.echo(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "out": str(repo / ".absicht"),
                    "units": [unit.model_dump(mode="json") for unit in marker.units],
                }
            )
        )
    else:
        count = len(marker.units)
        typer.echo(f"wrote {repo / '.absicht'} ({count} unit{'s' if count != 1 else ''})")


def _design_url(store: Path, repo: Path) -> str:
    """The marker's `design` field: the store root, spelled relative to the
    repo receiving the marker.

    The one spelling absicht's own store resolution can follow back from a
    marker today — `resolve_store` reads a relative target against the
    marker's directory, so a marker and the store it names travel together,
    and a remote design would be refused until checking one out is supported.
    Lexical, like `resolve_store` itself: no symlink resolution, just the two
    places as they were named."""
    return Path(os.path.relpath(store, repo)).as_posix()


@marker_app.command("check")
def marker_check(
    ctx: typer.Context,
    repo: Annotated[Path, typer.Option("--repo", metavar="PATH")],
    json_output: JsonOption = False,
) -> None:
    """Fail if a marker disagrees with the store."""
    opts = options(ctx)
    _, design = _design(opts)
    try:
        findings = check_marker(design, repo)
    except MarkerError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    report = Report(findings=findings)
    if opts.json_output:
        typer.echo(json.dumps(report.render_json()))
    elif body := report.render_text():
        # Silence is the pass signal, the spelling `ab check` uses.
        typer.echo(body)
    raise typer.Exit(report.exit_code(strict=False))


@marker_app.command("stamp")
def marker_stamp(
    ctx: typer.Context,
    repo: Annotated[Path, typer.Option("--repo", metavar="PATH")],
    unit: Annotated[str, typer.Option("--unit", metavar="REF")],
    milestone: Annotated[str, typer.Option("--milestone", metavar="REF")],
    json_output: JsonOption = False,
) -> None:
    """Move the watermark. Run from the commit that lands the work."""
    opts = options(ctx)
    root, design = _design(opts)
    if not any(m.id == milestone for m in design.milestones):
        # A stamp is evidence; a claim about a milestone that does not exist
        # is garbage a later `ab status` could not make sense of.
        typer.echo(f"--milestone {milestone!r}: no milestone in this store has that id", err=True)
        raise typer.Exit(ExitCode.USAGE)
    try:
        # The design store's HEAD, not --repo's: the watermark records where
        # the design had got to when the work landed, and --repo is the
        # implementing repo receiving the stamp — two different repos in
        # reference mode.
        design_rev = current_rev(root)
        marker = stamp_marker(repo, unit, milestone=milestone, design_rev=design_rev)
    except (MarkerError, GitError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    if opts.json_output:
        typer.echo(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "out": str(repo / ".absicht"),
                    "units": [watermark.model_dump(mode="json") for watermark in marker.units],
                }
            )
        )
    else:
        typer.echo(f"stamped {unit} at {milestone} in {repo / '.absicht'}")
