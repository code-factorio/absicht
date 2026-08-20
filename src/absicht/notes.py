"""The capture channel: add, list, promote and drop the notes under ``notes/``.

A note is deliberately not an element: not part of the ``Design``, no state,
referenced by nothing, never packet input — an agent never sees a note. This
module is the whole lifecycle around that exclusion:

- ``add`` captures with near-zero friction: no title, no owner, no kind —
  the moment authoring a note asks for classification it stops being used;
- ``promote`` is the only way a note becomes design: the element is built by
  the same machinery ``ab new`` uses, and the note is stamped with
  ``promoted_to`` rather than destroyed, because the record of what a note
  became is the point of keeping it;
- ``drop`` deletes a note that never mattered, and refuses a promoted one.

The inbox's *reading* lives here too — ``age_text`` and ``inbox_headline``,
the pressure vocabulary a bare count is not — so the terminal list and the
site's inbox page spell one answer, never two that drift.

Identity is the one place in the store not derived from a slug: ``note:`` +
six lowercase base36 characters, drawn at random and collision-checked
against the store, never asked for — editing a note must not change its
identity, and asking for a name at capture time is the friction that stops
notes being written at all. The draw is injectable because a test must be
able to watch a collision re-draw; ids are identity, not secrets.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from absicht.codec import dump_element
from absicht.load import StoreResolutionError, load_store, resolve_store
from absicht.models.design import Element, Note, Ref
from absicht.new import NewError, create, editor_argv, run_editor, scaffold

_DIRECTORY = "notes"
"""Where a note file lives. A note's path is its id, so nothing has to store
one: `notes/<slug>.md` for `note:<slug>`."""

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
"""Base36, lowercase — the character set a note id's slug draws from."""

_WIDTH = 6
_SPACE = 36**_WIDTH


class NoteError(Exception):
    """Why a note was not added, promoted or dropped. A broken invocation, not a finding."""


def add(
    store: Path,
    body: str,
    *,
    created: date,
    ref: Ref | None = None,
    rng: random.Random | None = None,
    edit: bool = False,
) -> Note:
    """Capture one note: generate its id, write ``notes/<slug>.md``, return it.

    ``created`` and the draw behind the id are parameters, not clock or
    randomness reads — the clock belongs to the caller the way it does for
    every authoring command, and an injectable ``rng`` is what lets a test
    watch a collision re-draw. ``ref`` is validated as a ``Ref`` and never
    resolved: capture first, the reader can judge an anchor that names
    nothing yet.
    """
    root = _root(store)
    try:
        editor = editor_argv(edit)
    except NewError as exc:
        raise NoteError(str(exc)) from exc
    slug = _fresh_slug({note.id.removeprefix("note:") for note in _notes(root)}, rng)
    try:
        note = Note(
            id=f"note:{slug}",
            created_on=created,
            about=(ref,) if ref else (),
            text=body,
        )
    except ValidationError as exc:
        problems = "; ".join(
            f"{error['loc'][0]}: {error['msg']}" for error in exc.errors(include_url=False)
        )
        raise NoteError(f"cannot add note: {problems}") from exc
    path = _path(root, note)
    # The two drift halves `ab new` guards: an id the loaded store holds, and
    # a file sitting at the path about to be written — the same condition in
    # a healthy store, different ones once the two have drifted apart.
    if path.exists():
        raise NoteError(f"{path} already exists: ab note never overwrites")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_element(note), encoding="utf-8")
    if editor:
        run_editor(editor, path)
    return note


def get(store: Path, note_id: str) -> Note:
    """The note ``note_id`` names — ``ab note show``'s one job."""
    return _by_id(_root(store), note_id)


def select(
    store: Path, *, ref: Ref | None = None, include_promoted: bool = False
) -> tuple[Note, ...]:
    """The inbox: unpromoted notes, oldest first.

    ``include_promoted`` is ``--all``: a promoted note has left the inbox but
    is still in the store, still readable. Age order with the id as tiebreak
    is the deterministic spelling of "oldest first" (§6: age is the pressure
    a bare count is not).
    """
    root = _root(store)
    chosen = [
        note
        for note in _notes(root)
        if (include_promoted or note.promoted_to is None) and (ref is None or ref in note.about)
    ]
    return tuple(sorted(chosen, key=inbox_order))


def promote(store: Path, note_id: str, kind: str, slug: str) -> Element:
    """Turn the note into a real element and stamp ``promoted_to`` on it.

    The element is scaffolded and written by the same machinery ``ab new``
    uses — promotion is not a second authoring path, it is the first one with
    a birthplace. The note is then rewritten with ``promoted_to`` set: it
    leaves the inbox but is never destroyed, which is also why promoting an
    already-promoted note is refused.
    """
    root = _root(store)
    note = _by_id(root, note_id)
    if note.promoted_to is not None:
        raise NoteError(f"{note.id} is already promoted to {note.promoted_to}")
    try:
        element = scaffold(kind, slug)
        create(root, element)
    except NewError as exc:
        raise NoteError(str(exc)) from exc
    updated = note.model_copy(update={"promoted_to": element.id})
    _path(root, note).write_text(dump_element(updated), encoding="utf-8")
    return element


def drop(store: Path, note_id: str) -> None:
    """Delete the note file: it never mattered, and dropping is the one exit
    that leaves nothing behind. A promoted note is refused — the record of
    what it became must survive the inbox's cleanup."""
    root = _root(store)
    note = _by_id(root, note_id)
    if note.promoted_to is not None:
        raise NoteError(
            f"{note.id} was promoted to {note.promoted_to} and cannot be dropped: "
            "the record of what it became must survive"
        )
    _path(root, note).unlink()


# --- the inbox's reading -----------------------------------------------------------


def inbox_order(note: Note) -> tuple[date, str]:
    """The inbox's deterministic order: oldest first, the id as tiebreak —
    the one spelling of "oldest first" both readers (`ab note list`, the
    site's inbox page) sort by, so they cannot disagree."""
    return (note.created_on, note.id)


def age_text(created: date, today: date) -> str:
    """A rough human age — the pressure reading, not accounting.

    Approximate buckets (30-day months, 365-day years) are the point: "3
    months" is the reading the addendum's own example wants, and a day-exact
    figure would bury it in precision nobody acts on differently. ``today``
    is a parameter, never a clock read: the caller injects it the way every
    dated judgement in this project is injected.
    """
    days = (today - created).days
    if days <= 0:
        return "today"
    if days < 14:
        return _plural(days, "day")
    if days < 60:
        return _plural(days // 7, "week")
    if days < 365:
        return _plural(days // 30, "month")
    return _plural(days // 365, "year")


def inbox_headline(selected: Sequence[Note], today: date) -> str:
    """`N notes, oldest X`: the count and the age of the oldest, nothing else
    — the useful pressure a bare count is not, shared by the terminal list
    and the site's inbox page so the two spell one headline. ``selected``
    arrives already in ``inbox_order`` (both callers sort with it), so the
    first entry *is* the oldest."""
    if not selected:
        return "0 notes"
    count = len(selected)
    oldest = age_text(selected[0].created_on, today)
    return f"{count} note{'s' if count != 1 else ''}, oldest {oldest}"


def _plural(count: int, unit: str) -> str:
    return f"{count} {unit}{'s' if count != 1 else ''}"


def _root(store: Path) -> Path:
    """Resolve the store location the one way every command does."""
    try:
        return resolve_store(store)
    except StoreResolutionError as exc:
        raise NoteError(str(exc)) from exc


def _path(root: Path, note: Note) -> Path:
    """Where a note's file is. Derived, never stored: a note has no `source`
    because its id already says where it lives."""
    return root / _DIRECTORY / f"{note.id.removeprefix('note:')}.md"


def _notes(root: Path) -> tuple[Note, ...]:
    """The store's notes, through the same tolerant walk `ab check` reads."""
    return load_store(root).notes


def _by_id(root: Path, note_id: str) -> Note:
    for note in _notes(root):
        if note.id == note_id:
            return note
    raise NoteError(f"no note {note_id!r} in the store")


def _fresh_slug(taken: set[str], rng: random.Random | None) -> str:
    """Draw six base36 characters until they name no note the store holds.

    36^6 is ~2.2 billion names, so a collision is a redraw, never a question
    to the author — the id is generated, not asked for.
    """
    # A note id is identity, not a secret: predictability costs nothing, and
    # a cryptographic draw buys no property the store needs.
    draw = rng if rng is not None else random.Random()  # nosec B311
    while (slug := _draw(draw)) in taken:
        continue
    return slug


def _draw(rng: random.Random) -> str:
    """One uniform six-character draw: an integer in ``[0, 36**6)``, spelled wide."""
    value = rng.randrange(_SPACE)  # nosec B311 -- identity, not a secret
    digits = []
    while value:
        value, digit = divmod(value, 36)
        digits.append(_ALPHABET[digit])
    return _ALPHABET[0] * (_WIDTH - len(digits)) + "".join(reversed(digits))
