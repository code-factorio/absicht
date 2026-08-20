"""Step 2 — build, query, look at it.

``ab build`` folds the store into the one artifact everything downstream reads;
the rest of this group are projections of it.
"""

# Typer registers commands through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
from collections.abc import Sequence
from contextlib import suppress
from datetime import date
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
)
from absicht.diagram import build as build_diagram
from absicht.diagram import overlay_colours
from absicht.findings import ExitCode
from absicht.git import GitError
from absicht.layout import (
    LayoutError,
    compute,
    merge,
    missing,
    nodes,
    read_layout,
    write_layout,
)
from absicht.load import StoreResolutionError, resolve_store
from absicht.models.design import (
    FORMAT_VERSION,
    Behavior,
    Confidence,
    Design,
    Element,
    Lifecycle,
    Milestone,
    Question,
    Ref,
    State,
)
from absicht.render import (
    QUESTION_BLOCKING,
    Gap,
    SiteServer,
    UnknownRefError,
    generate_site,
    neighbourhood,
    owner_text,
    reasons_text,
    superseded_mark,
    trace_paths,
    worklist,
)
from absicht.resolve import Index, Scope, inherited_owners, scope_of

PANEL = "Step 2 — build, query, look at it"
"""Where these commands appear in `ab --help`."""


def _design(opts: GlobalOptions) -> tuple[Path, Design]:
    """The load → resolve path every command needing the resolved design
    shares (this group's queries, `packet` in the handoff group): the
    resolved store root alongside the `Design`, because `layout` both reads
    the graph and writes `layout.yaml` back into the store it came from.

    One spelling of the three ways a query invocation breaks: no store, or a
    `--rev` that does not resolve / a store outside any repository (git reads,
    not findings), are `USAGE`; a store whose files did not all load is
    `build`'s `FINDINGS`-level refusal — a partial artifact is not an answer
    to a query either (docs/tasks/21-show.md's reuse rule).
    """
    try:
        root = resolve_store(opts.store)
        design = build_design(root, rev=opts.rev)
    except (StoreResolutionError, GitError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    except BuildError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.FINDINGS) from exc
    return root, design


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
    _, design = _design(opts)
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
        typer.echo(json.dumps({"format_version": FORMAT_VERSION, "out": str(out)}))
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
            json.dumps({"format_version": FORMAT_VERSION, "out": str(out), "stale": not fresh}),
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
    _, design = _design(opts)
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


_KIND_FIELDS: dict[Kind, str] = {
    Kind.TERM: "glossary",
    Kind.ACTOR: "actors",
    Kind.GOAL: "goals",
    Kind.REQ: "requirements",
    Kind.QUALITY: "qualities",
    Kind.CONSTRAINT: "constraints",
    Kind.BEHAVIOR: "behaviors",
    Kind.COMPONENT: "components",
    Kind.INTERFACE: "interfaces",
    Kind.DATA: "data_entities",
    Kind.RESOURCE: "resources",
    Kind.LIBRARY: "libraries",
    Kind.EXTERNAL: "external_services",
    Kind.ASSUMPTION: "assumptions",
    Kind.DECISION: "decisions",
    Kind.QUESTION: "questions",
    Kind.REJECTION: "rejections",
    Kind.MILESTONE: "milestones",
}
"""The `Design` field each kind's elements live in. Spelled out rather than
derived: a kind's ref prefix and its collection name agree often enough to
look like a rule (`term`/`glossary`, `req`/`requirements`) and never enough
to be one."""


def _milestone_scope(design: Design, ref: str | None) -> frozenset[Ref] | None:
    """The `scope` of the milestone `ref` names; `None` without `--milestone`.

    An unknown ref — nothing by that id, or an element of another kind — is
    `USAGE`, the exit-code table's broken invocation, rather than an empty
    answer a script would read as "the milestone scopes nothing".
    """
    if ref is None:
        return None
    milestone = next((m for m in design.milestones if m.id == ref), None)
    if milestone is None:
        typer.echo(f"--milestone {ref!r}: no milestone in this store has that id", err=True)
        raise typer.Exit(ExitCode.USAGE)
    return frozenset(milestone.scope)


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
    lifecycle: Annotated[
        Lifecycle | None,
        typer.Option(
            "--lifecycle", help="Behaviors only: still how the system works, or replaced."
        ),
    ] = None,
    scope: Annotated[
        Scope | None,
        typer.Option("--scope", help="Behaviors only: the derived local/system classification."),
    ] = None,
    output_format: Annotated[
        ListFormat,
        typer.Option("--format", help="ids for piping."),
    ] = ListFormat.TEXT,
    json_output: JsonOption = False,
) -> None:
    """List elements of one kind, filtered."""
    if owner is not None and unowned:
        typer.echo("--owner and --unowned are mutually exclusive", err=True)
        raise typer.Exit(ExitCode.USAGE)
    if lifecycle is not None and kind is not Kind.BEHAVIOR:
        typer.echo(f"--lifecycle filters behaviors' second axis; a {kind.value} has none", err=True)
        raise typer.Exit(ExitCode.USAGE)
    if scope is not None and kind is not Kind.BEHAVIOR:
        typer.echo(
            f"--scope filters behaviors' derived classification; a {kind.value} has none",
            err=True,
        )
        raise typer.Exit(ExitCode.USAGE)
    opts = options(ctx)
    _, design = _design(opts)
    milestone_scope = _milestone_scope(design, milestone)
    states = frozenset(state) if state else None
    tags = frozenset(tag) if tag else None
    index = Index(design)
    orphans = frozenset(index.orphaned(kind.value)) if orphaned else None
    # Owner inheritance joins the owner filters: an unowned `unknown` with
    # exactly one referencing owner answers to that owner, so it groups under
    # `--owner` and leaves `--unowned`. One map, the same one `ab gaps` reads.
    inherited = inherited_owners(index)
    elements: tuple[Element, ...] = getattr(design, _KIND_FIELDS[kind])
    # Every filter is a predicate AND over one kind, applied in id order — the
    # stable, deterministic answer the spec's no-sort-flag scope asks for.
    selected = [
        element
        for element in sorted(elements, key=lambda element: element.id)
        if (states is None or element.state in states)
        and (confidence is None or element.confidence is confidence)
        and (owner is None or element.owner == owner or inherited.get(element.id) == owner)
        and (not unowned or (element.owner is None and element.id not in inherited))
        and (tags is None or not tags.isdisjoint(element.tags))
        and (milestone_scope is None or element.id in milestone_scope)
        and (orphans is None or element.id in orphans)
        and (
            lifecycle is None or (isinstance(element, Behavior) and element.lifecycle is lifecycle)
        )
        and (scope is None or (isinstance(element, Behavior) and scope_of(element) is scope))
    ]
    output = effective_format(ctx, output_format, opts.json_output, json_member=ListFormat.JSON)
    if output is ListFormat.JSON:
        typer.echo(
            json.dumps(
                {
                    "format_version": FORMAT_VERSION,
                    "kind": kind.value,
                    "elements": [_element_json(element) for element in selected],
                }
            )
        )
    elif selected:
        # Both prose formats stay silent on an empty answer: a lone blank
        # line would hand `xargs` one empty argument where no id is.
        if output is ListFormat.IDS:
            typer.echo("\n".join(element.id for element in selected))
        else:
            width = max(len(element.id) for element in selected)
            typer.echo("\n".join(_row(element, width=width) for element in selected))


def _element_json(element: Element) -> dict[str, object]:
    """One listed element as json: the element itself, plus — for a behavior,
    beside its own fields — the derived classification the `--scope` filter
    keyed on (derived values appear in `--json`, never in a file an author
    edits)."""
    dump: dict[str, object] = element.model_dump(mode="json")
    if isinstance(element, Behavior):
        dump["scope"] = scope_of(element).value
    return dump


def _row(element: Element, *, width: int) -> str:
    """One `list` row: id, state, then — for a behavior, the derived scope the
    column exists to triage by — then the title, marked when the element is no
    longer how the system works."""
    columns = [element.id.ljust(width), element.state]
    if isinstance(element, Behavior):
        columns.append(scope_of(element).value)
    columns.append(f"{element.title}{superseded_mark(element)}")
    return "  ".join(columns)


def _blocks(element: Element, target: Element) -> bool:
    """Whether the gap ``element`` blocks ``target``, directly.

    Two edges say "blocks": a question's own ``blocks``, and — for a milestone
    target — the gaps its ``unresolved`` knowingly leaves open. Nothing
    transitive: the spec's "only gaps that block this element or milestone"
    names no closure, and walking the ref graph outward would soon claim most
    of the store blocks the rest.
    """
    if isinstance(element, Question) and target.id in element.blocks:
        return True
    return isinstance(target, Milestone) and element.id in target.unresolved


def _gap_json(gap: Gap) -> dict[str, object]:
    """One worklist entry as json: the annotation first, the element it is
    about alongside, so a consumer never has to re-read it with `ab show`."""
    return {
        "ref": gap.element.id,
        "reasons": list(gap.reasons),
        "blocks": list(gap.blocks),
        "expires_on": gap.expires_on.isoformat() if gap.expires_on is not None else None,
        # The derived owner, additive per the envelope rules: null unless the
        # entry is an unowned `unknown` with exactly one referencing owner.
        "owner_inherited": gap.owner_inherited,
        "element": gap.element.model_dump(mode="json"),
    }


@app.command(rich_help_panel=PANEL)
def gaps(
    ctx: typer.Context,
    kind: Annotated[Kind | None, typer.Option("--kind")] = None,
    owner: Annotated[str | None, typer.Option("--owner", metavar="WHO")] = None,
    blocks_something: Annotated[
        bool,
        typer.Option("--blocking-only", help="Only questions something waits on."),
    ] = False,
    blocking: Annotated[
        str | None,
        typer.Option(
            "--blocking", metavar="REF", help="Only gaps blocking this element or milestone."
        ),
    ] = None,
    output_format: Annotated[PlainFormat, typer.Option("--format")] = PlainFormat.TEXT,
    json_output: JsonOption = False,
) -> None:
    """Everything unfinished, as a worklist.

    `unknown`, `observed` and `delegated` elements, open questions, unowned
    elements, expired external services, and behaviors with no observations.
    An unowned `unknown` with exactly one referencing owner reports that
    owner, marked inherited.
    """
    opts = options(ctx)
    _, design = _design(opts)
    target: Element | None = None
    if blocking is not None:
        target = Index(design).get(blocking)
        if target is None:
            typer.echo(f"--blocking {blocking!r}: no element in this store has that id", err=True)
            raise typer.Exit(ExitCode.USAGE)
    # Every filter is a predicate AND over the unioned worklist, applied in
    # the id order `worklist` produces — the same stable answer `list` gives.
    # `--owner` matches the inherited owner too, like `list`'s: an unowned
    # `unknown` that answers to its single referencing owner is platform's
    # gap as much as qa's owned one is qa's.
    selected = [
        gap
        for gap in worklist(design, today=date.today())
        if (kind is None or gap.element.id.startswith(f"{kind.value}:"))
        and (owner is None or gap.element.owner == owner or gap.owner_inherited == owner)
        and (not blocks_something or QUESTION_BLOCKING in gap.reasons)
        and (target is None or _blocks(gap.element, target))
    ]
    output = effective_format(ctx, output_format, opts.json_output, json_member=PlainFormat.JSON)
    if output is PlainFormat.JSON:
        typer.echo(
            json.dumps(
                {"format_version": FORMAT_VERSION, "gaps": [_gap_json(gap) for gap in selected]}
            )
        )
    elif selected:
        # Empty stays silent, like `list`: no blank line where a row would be.
        # A row with an inherited owner names it between the reasons and the
        # title — the one annotation only some rows carry.
        width = max(len(gap.element.id) for gap in selected)
        rows = []
        for gap in selected:
            columns = [gap.element.id.ljust(width), reasons_text(gap)]
            if annotation := owner_text(gap):
                columns.append(annotation)
            columns.append(gap.element.title)
            rows.append("  ".join(columns))
        typer.echo("\n".join(rows))


@app.command(rich_help_panel=PANEL)
def trace(
    ctx: typer.Context,
    ref: Annotated[str, typer.Argument(metavar="REF", help="Where to start.")],
    to: Annotated[
        str | None,
        typer.Option("--to", metavar="REF", help="Paths between two elements."),
    ] = None,
    up: Annotated[
        bool,
        typer.Option("--up", help="Follow refs pointing at REF. Default: both directions."),
    ] = False,
    down: Annotated[
        bool,
        typer.Option("--down", help="Follow REF's own refs. Default: both directions."),
    ] = False,
    output_format: Annotated[TraceFormat, typer.Option("--format")] = TraceFormat.TEXT,
    json_output: JsonOption = False,
) -> None:
    """Traceability paths through the graph.

    Requirement to component to seam to decision, in either direction.
    """
    opts = options(ctx)
    _, design = _design(opts)
    try:
        traced = trace_paths(design, ref, to=to, up=up, down=down)
    except UnknownRefError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    output = effective_format(ctx, output_format, opts.json_output, json_member=TraceFormat.JSON)
    if output is TraceFormat.JSON:
        typer.echo(json.dumps(traced.render_json()))
    elif output is TraceFormat.MERMAID:
        typer.echo(traced.render_mermaid())
    elif text := traced.render_text():
        # Empty stays silent, like `list` and `gaps`: no blank line where a
        # path would be.
        typer.echo(text)


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
    opts = options(ctx)
    if serve and not 1 <= port <= 65535:
        typer.echo("--port must be between 1 and 65535", err=True)
        raise typer.Exit(ExitCode.USAGE)
    # One command, two outputs. A bare invocation is the site (docs/tasks/
    # 26-render-site.md); an explicit `--format` or any `--overlay` asks for
    # the diagram half (27-render-diagrams.md). The default `--format svg` is
    # the diagram's own default, not a site selector, so only an explicit pass
    # or an overlay routes there.
    source = ctx.get_parameter_source("output_format")
    wants_diagram = bool(overlay) or (source is not None and source.name != "DEFAULT")
    if serve and wants_diagram:
        # `--serve` is the site's preview loop; pretending to watch one-shot
        # diagram files would promise rebuilds that never happen.
        typer.echo("--serve previews the site; diagrams are written once, not watched", err=True)
        raise typer.Exit(ExitCode.USAGE)
    root, design = _design(opts)
    if wants_diagram:
        _render_diagrams(opts, root, design, out, output_format, overlay or (), scope)
        return
    try:
        pages = generate_site(design, out, today=date.today(), scope=scope, notes=design.notes)
    except UnknownRefError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    if opts.json_output:
        typer.echo(
            json.dumps({"format_version": FORMAT_VERSION, "out": str(out), "pages": len(pages)})
        )
    else:
        typer.echo(f"wrote {out} ({len(pages)} pages)")
    if not serve:
        return

    # The rebuild re-reads the store rather than reusing this run's design —
    # picking up the change is the point, notes included. A frozen --rev is
    # not watched: editing the working tree under a pinned revision would
    # trigger rebuilds that cannot change anything.
    def rebuild() -> None:
        fresh = build_design(root, rev=opts.rev)
        generate_site(fresh, out, today=date.today(), scope=scope, notes=fresh.notes)

    server = SiteServer(out, port, watch=None if opts.rev is not None else root, rebuild=rebuild)
    typer.echo(f"serving {out} at http://127.0.0.1:{port} (Ctrl-C to stop)", err=True)
    # Ctrl-C is the one way out of a preview; its daemon threads die with the
    # process, so suppressing the interrupt here is the whole shutdown.
    with suppress(KeyboardInterrupt):
        server.serve()


def _render_diagrams(
    opts: GlobalOptions,
    root: Path,
    design: Design,
    out: Path,
    output_format: DiagramFormat,
    overlays: Sequence[Overlay],
    scope: str | None,
) -> None:
    """The diagram half of ``render``: one file per variant under ``out``, the
    overlay spelling the file's name. Overlays are separate output variants —
    one visual result per overlay, no blend — so an invocation that names any
    writes exactly those; only an overlay-less one writes the uncoloured
    ``diagram.<format>``.

    Unpinned positions are ``FINDINGS`` — the same verdict ``ab layout
    --check`` gives the same store — and an unknown ``--scope`` ref is
    ``USAGE``, the lookup miss every ref-taking command maps there.
    """
    try:
        picture = build_diagram(design, root, scope=scope)
    except UnknownRefError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.USAGE) from exc
    except LayoutError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.FINDINGS) from exc
    render = {
        DiagramFormat.SVG: picture.render_svg,
        DiagramFormat.MERMAID: picture.render_mermaid,
        DiagramFormat.D2: picture.render_d2,
    }[output_format]
    # dict.fromkeys keeps only the first spelling of a repeated overlay: a
    # second file of identical bytes would read as a variant that did nothing.
    variants: list[Overlay | None] = list(dict.fromkeys(overlays)) or [None]
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for variant in variants:
        colouring = None if variant is None else overlay_colours(variant.value, design, root=root)
        name = f"diagram{'-' + variant.value if variant is not None else ''}.{output_format.value}"
        (out / name).write_text(render(colouring) + "\n", encoding="utf-8")
        written.append(name)
    if opts.json_output:
        typer.echo(
            json.dumps({"format_version": FORMAT_VERSION, "out": str(out), "diagrams": written})
        )
    else:
        typer.echo("\n".join(f"wrote {out / name}" for name in written))


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
    memory never forms. The default and `--recompute` place only elements
    without a pinned position; `--recompute-all` throws the pins away.
    """
    if check_positions and (recompute or recompute_all):
        typer.echo("--check reads the pinned positions; it does not recompute them", err=True)
        raise typer.Exit(ExitCode.USAGE)
    if recompute and recompute_all:
        typer.echo(
            "--recompute keeps pinned positions and --recompute-all discards them; pick one",
            err=True,
        )
        raise typer.Exit(ExitCode.USAGE)
    opts = options(ctx)
    root, design = _design(opts)
    try:
        pinned = read_layout(root)
    except LayoutError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(ExitCode.FINDINGS) from exc
    if check_positions:
        lacking = missing(design, pinned)
        if opts.json_output:
            typer.echo(json.dumps({"format_version": FORMAT_VERSION, "missing": list(lacking)}))
        elif lacking:
            typer.echo("\n".join(f"no position for {ref}" for ref in lacking))
        else:
            typer.echo(f"every diagram element has a position ({len(nodes(design))})")
        if lacking:
            raise typer.Exit(ExitCode.FINDINGS)
        return
    fresh = compute(design, seed=seed)
    result = fresh if recompute_all else merge(pinned, fresh)
    path = write_layout(root, result)
    kept = {position.ref for position in pinned.positions}
    added = sum(1 for position in result.positions if position.ref not in kept)
    if opts.json_output:
        typer.echo(
            json.dumps(
                {
                    "format_version": FORMAT_VERSION,
                    "out": str(path),
                    "added": added,
                    "total": len(result.positions),
                }
            )
        )
    else:
        typer.echo(f"wrote {path} ({added} added, {len(result.positions)} positions)")
