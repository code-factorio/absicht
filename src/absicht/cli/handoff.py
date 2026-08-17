"""Step 3 — hand work to an agent.

The packet is the unit of output and the thing the whole project is a bet on.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from absicht.cli._app import app
from absicht.cli._common import (
    DEFAULT_FEATURES_DIR,
    DEFAULT_PACKET_DIR,
    JsonOption,
    PacketFormat,
    effective_format,
    options,
    utc_now_iso,
)
from absicht.cli.query import _design
from absicht.findings import ExitCode
from absicht.gherkin import render_feature, scenario_digest
from absicht.git import GitError, current_rev, repo_root, resolve_rev
from absicht.models import SCHEMA_VERSION, Criterion, Design, Packet, PacketLock
from absicht.packet import PacketFindingError, PacketUsageError, assemble
from absicht.render import packet_markdown
from absicht.resolve import Index
from absicht.runstore import RunStoreError, packet_id, record_packet

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
        typer.Option(
            "--features-dir",
            metavar="DIR",
            help="Where the .feature files land: under --out, or under the cwd with --stdout.",
        ),
    ] = DEFAULT_FEATURES_DIR,
    rev: Annotated[
        str | None,
        typer.Option("--rev", metavar="REF", help="Build from the store at a revision."),
    ] = None,
    seal: Annotated[
        bool,
        typer.Option(
            "--seal",
            help=(
                "Write packet.lock (design rev, scenario digest) into --out for ab verify. "
                "Needs --features; refuses --stdout."
            ),
        ),
    ] = False,
    target_agent: Annotated[
        str | None,
        typer.Option(
            "--target-agent",
            metavar="WHO",
            help="Who the packet is handed to; recorded with the issuance in the run store.",
        ),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Assemble the brief for one milestone.

    Milestone scope at full fidelity, one ring of neighbouring contracts, the
    behaviors this slice must newly satisfy and the active ones it must not
    break (composition expanded one hop), the decisions and NFRs that must
    hold, explicit freedoms, known unknowns, and the rejections that must not
    be re-proposed.
    """
    opts = options(ctx)
    _refuse(seal=seal, to_stdout=to_stdout, features=features, horizon=horizon)
    # The command's own --rev and the root's mean the same thing here: either
    # spelling builds the same revision, so the command's wins when both are
    # given and `_design` sees one resolved answer either way.
    at = rev if rev is not None else opts.rev
    root, design = _design(replace(opts, rev=at))
    assembled = _assembled(design, milestone, horizon=horizon, include=include, exclude=exclude)

    out_dir = out if out is not None else DEFAULT_PACKET_DIR / milestone.removeprefix("milestone:")
    rendered = _feature_files(design, assembled.criteria) if features else {}
    # Features are a real directory write even under --stdout: the packet body
    # is what goes to stdout, not the files the digest seals.
    features_root = features_dir if to_stdout else out_dir / features_dir
    for name, content in rendered.items():
        target = features_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if seal:
        assembled = _sealed(assembled, rendered, at, root)
    _record_issuance(root, assembled, target_agent)

    output = effective_format(ctx, output_format, opts.json_output, json_member=PacketFormat.JSON)
    body = (
        assembled.model_dump_json(indent=2) + "\n"
        if output is PacketFormat.JSON
        else packet_markdown(assembled, features_dir=str(features_dir) if features else None)
    )
    if to_stdout:
        # `nl=False`: the body ends in the newline a file gets, so stdout is
        # byte-identical to what a write would have produced.
        typer.echo(body, nl=False)
        return
    _write_artifacts(
        assembled,
        body,
        out_dir=out_dir,
        output=output,
        rendered=rendered,
        features_root=features_root,
        sealed=seal,
        json_output=opts.json_output,
    )


def _refuse(*, seal: bool, to_stdout: bool, features: bool, horizon: int) -> None:
    """The invocations that defeat their own purpose, each refused before any
    store is read: a seal with nowhere durable to put the lock, a seal over no
    rendered scenarios (silently turning features back on would override an
    explicit `--no-features`), and a negative ring count."""
    if seal and to_stdout:
        typer.echo(
            "--seal writes packet.lock into --out; --stdout leaves nowhere durable to put it",
            err=True,
        )
        raise typer.Exit(ExitCode.USAGE)
    if seal and not features:
        typer.echo(
            "--seal seals the rendered .feature files; --no-features leaves nothing to seal",
            err=True,
        )
        raise typer.Exit(ExitCode.USAGE)
    if horizon < 0:
        typer.echo("--horizon counts rings out from the scope; it cannot be negative", err=True)
        raise typer.Exit(ExitCode.USAGE)


def _assembled(
    design: Design,
    milestone: str,
    *,
    horizon: int,
    include: list[str] | None,
    exclude: list[str] | None,
) -> Packet:
    """`absicht.packet.assemble` with its two failure vocabularies mapped to
    the exit-code table: a broken invocation is `USAGE`, a milestone that
    names no scope is `FINDINGS` — a true statement about the design."""
    try:
        return assemble(
            design,
            Index.from_design(design),
            milestone,
            horizon=horizon,
            include=frozenset(include or ()),
            exclude=frozenset(exclude or ()),
        )
    except PacketUsageError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    except PacketFindingError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.FINDINGS) from exc


def _sealed(packet: Packet, rendered: dict[str, str], at: str | None, root: Path) -> Packet:
    """The packet stamped with what `packet.lock` will carry — the design rev
    and the digest of the files just rendered — so the two cannot drift."""
    try:
        repo = repo_root(root)
        design_rev = resolve_rev(at, repo) if at is not None else current_rev(repo)
    except GitError as exc:
        typer.echo(f"--seal needs the store's git history: {exc}", err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    return packet.model_copy(
        update={"design_rev": design_rev, "scenarios_digest": scenario_digest(rendered)}
    )


def _record_issuance(root: Path, packet: Packet, target_agent: str | None) -> None:
    """Packet issuance into the run store — addendum §8's first tuple, beside
    the design store, never in git.

    Recorded for every assembly, sealed or not: an unsealed packet is still
    handed to an agent, and its empty design rev keeps the digest's id and
    the row's rev agreeing. The timestamp is this layer's clock — the library
    below stays clock-free. A store this ab cannot safely write stops the
    command before it delivers anything: better a named exit 4 than history
    quietly lost."""
    try:
        record_packet(
            root,
            packet_id=packet_id(packet.milestone, packet.design_rev),
            milestone=packet.milestone,
            design_rev=packet.design_rev,
            issued_at=utc_now_iso(),
            target_agent=target_agent,
        )
    except RunStoreError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.SCHEMA_MISMATCH) from exc


def _write_artifacts(
    packet: Packet,
    body: str,
    *,
    out_dir: Path,
    output: PacketFormat,
    rendered: dict[str, str],
    features_root: Path,
    sealed: bool,
    json_output: bool,
) -> None:
    """The durable half of the command: the packet body into `--out`, the
    `packet.lock` beside it when sealed, and a status line naming everything
    written — the `--json` envelope of `00-conventions.md` when asked for."""
    out_dir.mkdir(parents=True, exist_ok=True)
    body_path = out_dir / f"packet.{output.value}"
    body_path.write_text(body, encoding="utf-8")
    written = [f"wrote {body_path}"]
    if rendered:
        count = len(rendered)
        written.append(f"wrote {features_root} ({count} feature file{'s' if count > 1 else ''})")
    if sealed:
        # JSON, not YAML: machine-read by `ab verify`, never hand-authored,
        # so it sides with the artifact rather than the store's files. The
        # `PacketLock` model is the one spelling of it — `ab verify`'s loader
        # reads the file back through the same model, so the two ends cannot
        # drift.
        lock_path = out_dir / "packet.lock"
        lock_path.write_text(
            PacketLock(
                design_rev=packet.design_rev, scenarios_digest=packet.scenarios_digest
            ).model_dump_json(indent=2)
            + "\n",
            encoding="utf-8",
        )
        written.append(f"wrote {lock_path}")
    if json_output:
        envelope: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "out": str(out_dir),
            "packet": str(body_path),
        }
        if rendered:
            envelope["features"] = str(features_root)
        if sealed:
            envelope["lock"] = str(out_dir / "packet.lock")
        typer.echo(json.dumps(envelope))
    else:
        typer.echo("\n".join(written))


def _feature_files(design: Design, criteria: tuple[Criterion, ...]) -> dict[str, str]:
    """The ``.feature`` files for a packet's criteria: one per story behind
    them, named by the story's slug, criteria in the order the packet carries.

    The file names are part of what ``scenario_digest`` hashes, so they are
    the contract ``packet.lock`` seals — ``ab features`` (docs/tasks/
    33-features.md) walks its own milestone but must not spell them
    differently. Every criterion a packet carries is anchored to a story of
    the design, ``assemble``'s own selection rule."""
    stories = {story.id: story for story in design.stories}
    grouped: dict[str, list[Criterion]] = {}
    for criterion in criteria:
        grouped.setdefault(criterion.id.rsplit("#", 1)[0], []).append(criterion)
    return {
        f"{story_id.removeprefix('story:')}.feature": render_feature(
            stories[story_id], tuple(group)
        )
        for story_id, group in grouped.items()
    }


def _write_features(out: Path, rendered: dict[str, str], *, json_output: bool) -> None:
    """The durable half of ``features``: one file per rendered story under
    ``out``, the ``--json`` envelope of ``00-conventions.md`` when asked for.

    A milestone with no behavioural criteria renders nothing and writes
    nothing — no empty directory, and (like ``list``) no lone status line
    where files would be.
    """
    if rendered:
        out.mkdir(parents=True, exist_ok=True)
        for name, content in rendered.items():
            (out / name).write_text(content, encoding="utf-8")
    if json_output:
        typer.echo(
            json.dumps(
                {"schema_version": SCHEMA_VERSION, "out": str(out), "files": sorted(rendered)}
            )
        )
    elif rendered:
        count = len(rendered)
        typer.echo(f"wrote {out} ({count} feature file{'s' if count > 1 else ''})")


def _check_features(
    out: Path,
    milestone: str,
    rendered: dict[str, str],
    *,
    json_output: bool,
    verdict_stderr: bool,
) -> None:
    """Compare a fresh render against the ``.feature`` files at ``out``, never
    writing them: the guardrail behind "output is generated, never authored",
    and how CI catches a hand-edit.

    The whole ``*.feature`` set is compared, both directions — a file the
    store no longer renders has drifted as surely as an edited line — while
    other files beside them (step definitions) are not this command's to
    judge. Raw bytes, not text, so a corrupted file is drift rather than a
    decode crash. When ``--stdout`` occupies stdout with the rendered files,
    the verdict moves to stderr, the way ``build --check``'s does.
    """
    on_disk = {path.name for path in out.glob("*.feature")}
    why: dict[str, str] = {}
    for name in sorted(rendered.keys() | on_disk):
        if name not in rendered:
            why[name] = "is on disk but not rendered"
        elif name not in on_disk:
            why[name] = "is rendered but not on disk"
        elif (out / name).read_bytes() != rendered[name].encode("utf-8"):
            why[name] = "differs from a fresh render"
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "out": str(out),
                    "stale": bool(why),
                    "files": sorted(why),
                }
            ),
            err=verdict_stderr,
        )
    elif not why:
        typer.echo(f"{out} is up to date", err=verdict_stderr)
    else:
        for name in sorted(why):
            typer.echo(f"stale: {out / name} {why[name]}", err=verdict_stderr)
        typer.echo(f"run ab features {milestone} --out {out} to refresh", err=verdict_stderr)
    if why:
        raise typer.Exit(ExitCode.FINDINGS)


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
    json_output: JsonOption = False,
) -> None:
    """Render behavioural criteria to Gherkin, without the rest of the packet.

    Output is generated, never authored: an agent implements step definitions and
    may not touch these files.
    """
    opts = options(ctx)
    _, design = _design(opts)
    # `ab packet`'s own selection with the horizon folded away: the same
    # milestone resolution, the same criteria walk, the same refusals. This is
    # the Gherkin slice of a packet — the files `--seal` digests — so a
    # milestone that qualifies for one command qualifies for the other.
    assembled = _assembled(design, milestone, horizon=0, include=None, exclude=None)
    rendered = _feature_files(design, assembled.criteria)

    if to_stdout:
        # One `# path` header per file — a Gherkin comment, so the stream stays
        # parseable while an agent piping it can still split it back into files.
        for name in sorted(rendered):
            typer.echo(f"# {out / name}")
            typer.echo(rendered[name], nl=False)
    if check_stale:
        _check_features(
            out, milestone, rendered, json_output=opts.json_output, verdict_stderr=to_stdout
        )
        return
    if to_stdout:
        return
    _write_features(out, rendered, json_output=opts.json_output)
