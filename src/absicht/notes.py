"""The capture channel: add, list, promote and drop the notes under ``notes/``.

A note is deliberately not an element (addendum §6): not part of the
``Design``, no state, referenced by nothing, never packet input — an agent
never sees a note. This module is the whole lifecycle around that exclusion:

- ``add`` captures with near-zero friction: no title, no owner, no kind —
  the moment authoring a note asks for classification it stops being used;
- ``promote`` is the only way a note becomes design: the element is built by
  the same machinery ``ab new`` uses, and the note is stamped with
  ``promoted_to`` rather than destroyed, because the record of what a note
  became is the point of keeping it;
- ``drop`` deletes a note that never mattered, and refuses a promoted one.

Identity is the one place in the store not derived from a slug: ``note:`` +
six lowercase base36 characters, drawn at random and collision-checked
against the store, never asked for — editing a note must not change its
identity, and asking for a name at capture time is the friction the addendum
forbids. The draw is injectable because a test must be able to watch a
collision re-draw; ids are identity, not secrets.
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from absicht.codec import dump_element
from absicht.load import StoreResolutionError, load_store, resolve_store
from absicht.models import Element, Note, Ref
from absicht.new import NewError, create, editor_argv, run_editor, scaffold

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
    resolved: capture first (§6's friction rule), the reader can judge an
    anchor that names nothing yet.
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
            created=created,
            ref=ref,
            body=body,
            source=f"notes/{slug}.md",
        )
    except ValidationError as exc:
        problems = "; ".join(
            f"{error['loc'][0]}: {error['msg']}" for error in exc.errors(include_url=False)
        )
        raise NoteError(f"cannot add note: {problems}") from exc
    path = root / "notes" / f"{slug}.md"
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
        if (include_promoted or note.promoted_to is None) and (ref is None or note.ref == ref)
    ]
    return tuple(sorted(chosen, key=lambda note: (note.created, note.id)))


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
    assert note.source, "a loaded note always carries its store-relative path"
    updated = note.model_copy(update={"promoted_to": element.id})
    (root / note.source).write_text(dump_element(updated), encoding="utf-8")
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
    (root / note.source).unlink()


def _root(store: Path) -> Path:
    """Resolve the store location the one way every command does."""
    try:
        return resolve_store(store)
    except StoreResolutionError as exc:
        raise NoteError(str(exc)) from exc


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
