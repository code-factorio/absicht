"""Scaffold one element: the id from the slug, every other field at its default.

``ab new`` is a scaffolding command, not a wizard (docs/tasks/11-new.md): it
builds the minimal valid instance of the kind's model — ``Component(id=...,
title=..., state=..., owner=...)`` and friends — renders it through the codec
and writes it into the store, refusing to overwrite anything, the same line
``ab init`` holds.

Never-overwrite has two halves, because a store and its files can drift: the
id check goes through ``load`` + ``resolve``, the file check through the
filesystem. A renamed file still holding the old id fails the first, an
unparsable file no index ever saw fails the second.

Models with required fields no default exists for (``Interface.style``,
``QualityRequirement.attribute``, ``Resource.resource_kind`` and the rest)
are scaffolded rather than refused: ``ab new`` fills each with a placeholder
— the enum's first declared member where an enum is involved, an obviously
replaceable string where the field is free text — and says so in a comment in
the body, never a value that would pass ``check`` unreviewed. The behavior
template additionally carries a worked observation example, commented out in
the body: the file is where an author first meets the format, and observation
ids are authored inline, never generated here.

``--edit`` shells out to ``$EDITOR`` on the written file. A command that says
it will open an editor and does not is worse than one that says why it
cannot, so an unset ``$EDITOR`` is an error — checked before anything is
written, so no half-edited file is left behind.
"""

from __future__ import annotations

import os
import shlex
import subprocess  # nosec B404 -- same bargain as absicht.git: argv lists, never a shell
from pathlib import Path

from pydantic import ValidationError

from absicht.codec import DIRECTORIES, dump_element
from absicht.load import StoreResolutionError, load_store, resolve_store
from absicht.models.design import (
    Actor,
    Assumption,
    Behavior,
    Component,
    ComponentLevel,
    Constraint,
    ConstraintKind,
    DataEntity,
    Decision,
    Element,
    ExternalService,
    Goal,
    Interface,
    InterfaceStyle,
    Library,
    Milestone,
    QualityAttribute,
    QualityRequirement,
    Question,
    Rejection,
    Requirement,
    Resource,
    ResourceKind,
    State,
    Term,
)
from absicht.resolve import Index, ResolveError, resolve


class NewError(Exception):
    """Why an element was not scaffolded. A broken invocation, not a finding."""


# The kind a caller names — a `Kind` value from the CLI surface, spelled as a
# plain string here because `absicht.cli` sits above this layer in the import
# stack — mapped to the model it scaffolds. Which directory that model is
# written to comes from `absicht.codec`'s `DIRECTORIES`, which is the store
# layout itself, so an element can never land in a directory `load` does not
# read.
_KINDS: dict[str, type[Element]] = {
    "term": Term,
    "actor": Actor,
    "goal": Goal,
    "req": Requirement,
    "quality": QualityRequirement,
    "constraint": Constraint,
    "behavior": Behavior,
    "component": Component,
    "interface": Interface,
    "data": DataEntity,
    "resource": Resource,
    "library": Library,
    "external": ExternalService,
    "assumption": Assumption,
    "decision": Decision,
    "question": Question,
    "rejection": Rejection,
    "milestone": Milestone,
}

_DIRECTORY_OF: dict[type[object], str] = {model: name for name, model in DIRECTORIES.items()}

_PLACEHOLDER = "replace me"

# The kinds whose model has required fields no default exists for, and the
# placeholders `ab new` fills them with: the enum's first declared member —
# the smallest honest choice rather than an editorial one — where an enum is
# involved, and `replace me` where the field is free text (no technology or
# trigger anyone would ship). `_placeholder_note` names every field in the
# body, so the file itself says what to replace.
_PLACEHOLDERS: dict[str, tuple[tuple[str, object], ...]] = {
    "term": (("definition", _PLACEHOLDER),),
    "goal": (("outcome", _PLACEHOLDER),),
    "req": (("statement", _PLACEHOLDER),),
    "quality": (("attribute", QualityAttribute.LATENCY),),
    "constraint": (
        ("statement", _PLACEHOLDER),
        ("constraint_kind", ConstraintKind.REGULATORY),
    ),
    "behavior": (("trigger", _PLACEHOLDER),),
    "component": (("level", ComponentLevel.SYSTEM),),
    "interface": (("style", InterfaceStyle.CALL),),
    "resource": (("resource_kind", ResourceKind.STORE), ("technology", _PLACEHOLDER)),
    "library": (("package", _PLACEHOLDER), ("ecosystem", _PLACEHOLDER)),
    "assumption": (("statement", _PLACEHOLDER),),
    "decision": (("choice", _PLACEHOLDER),),
    "question": (("question", _PLACEHOLDER),),
}


def scaffold(
    kind: str,
    slug: str,
    *,
    title: str | None = None,
    state: State = State.UNKNOWN,
    owner: str | None = None,
) -> Element:
    """Build the minimal valid instance of `kind`, with `id = f"{kind}:{slug}"`.

    `title` falls back to the slug — the name the caller just typed — because
    everything a human would fill differently is one `--edit` away; an
    explicit empty title still fails validation instead of being quietly
    replaced. A slug that breaks the id pattern, or any field the model
    refuses, is a `NewError` naming the culprit: the CLI maps it to `USAGE`,
    per the identity rules in docs/tasks/00-conventions.md.
    """
    try:
        model = _KINDS[kind]
    except KeyError:
        raise NewError(f"unknown kind {kind!r}: not one of {', '.join(_KINDS)}") from None
    fields: dict[str, object] = {
        "id": f"{kind}:{slug}",
        "title": title if title is not None else slug,
        "state": state,
        "owner": owner,
    }
    placeholders = _PLACEHOLDERS.get(kind, ())
    fields.update(placeholders)
    if placeholders:
        body = _placeholder_note(placeholders)
        if kind == "behavior":
            body += _observation_example(f"{kind}:{slug}")
        fields["body"] = body
    try:
        return model.model_validate(fields)
    except ValidationError as exc:
        problems = "; ".join(
            f"{error['loc'][0]}: {error['msg']}" for error in exc.errors(include_url=False)
        )
        raise NewError(f"cannot scaffold {kind} {slug!r}: {problems}") from exc


def _placeholder_note(fields: tuple[tuple[str, object], ...]) -> str:
    """The template comment that owns up to guessed fields, every one named."""
    named = ", ".join(f"{name}: {value}" for name, value in fields)
    return (
        f"<!-- {named} — placeholders `ab new` chose because the model has no "
        f"defaults for them; replace them before this element is trusted. -->\n"
    )


def _observation_example(behavior_id: str) -> str:
    """A worked observation, commented out in the template's body: `#obs-1`'s
    anchoring to this behavior — plus `outcome` and `timing`, which a
    `must_not` omits — reads easier as a filled-in example than as a rule,
    and the ids stay authored, never generated."""
    return (
        "<!--\n"
        "Observations are authored inline in the front matter above, anchored to\n"
        "this behavior by id; `ab new` never generates them:\n"
        "\n"
        "    observations:\n"
        f"      - id: {behavior_id}#obs-1\n"
        "        statement: Cache entry exists under sess:{id}\n"
        "        at: resource:session-cache\n"
        "        outcome: must\n"
        "        timing: immediate\n"
        "-->\n"
    )


def create(store: Path, element: Element, *, edit: bool = False) -> Path:
    """Write `element` into the store at its id's path, and return that path.

    `store` is the location the CLI was given — a directory in embedded mode,
    a `.absicht` marker in reference mode — resolved the one way
    `absicht.load` resolves stores, so a marker names the store written to.
    """
    slug = element.id.split(":", 1)[1]
    try:
        root = resolve_store(store)
    except StoreResolutionError as exc:
        raise NewError(str(exc)) from exc
    path = root / _DIRECTORY_OF[type(element)] / f"{slug}.md"
    if element.id in _ids(root):
        raise NewError(f"{element.id} already exists in the store at {root}")
    if path.exists():
        raise NewError(f"{path} already exists: ab new never overwrites")
    editor = editor_argv(edit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_element(element), encoding="utf-8")
    if editor:
        run_editor(editor, path)
    return path


def _ids(root: Path) -> dict[str, Element]:
    """Every id the store holds, through the same load-and-index path the
    reading commands use — so what `ab new` refuses to duplicate is exactly
    what `ab show` would have found."""
    try:
        design = resolve(load_store(root))
    except ResolveError as exc:
        raise NewError(f"{exc}; run ab init to scaffold one") from exc
    return Index(design).local


def editor_argv(edit: bool) -> list[str]:
    """The `$EDITOR` argv `--edit` will run, resolved before anything is written.

    `shlex.split` because `$EDITOR` may carry arguments ("code -w"); an unset
    or empty `$EDITOR` is a broken invocation, not a no-op the command
    silently swallows. Public because `absicht.notes`' `--edit` is the same
    bargain — write, then open the written file — and a second spelling of it
    would be the drift this module exists to prevent.
    """
    if not edit:
        return []
    editor = shlex.split(os.environ.get("EDITOR", ""))
    if not editor:
        raise NewError("--edit needs $EDITOR to name an editor; none is set")
    return editor


def run_editor(editor: list[str], path: Path) -> None:
    """Open the written file in the editor, in the foreground."""
    # Same bargain as absicht.git: an argv list, never a shell. The command
    # word comes from `$EDITOR` as data, so the partial-path check has
    # nothing literal to bite on — resolving the editor from PATH is the
    # point of the variable.
    completed = subprocess.run(  # nosec B603
        [*editor, str(path)],
        check=False,
    )
    if completed.returncode != 0:
        raise NewError(
            f"$EDITOR ({' '.join(editor)}) exited with {completed.returncode}: "
            f"{path} is written but was not edited"
        )
