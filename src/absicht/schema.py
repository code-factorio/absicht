"""Regenerate the JSON Schema files a store's files validate against.

``ab schema`` writes these so an editor can autocomplete and inline-flag
fields while an element is authored (docs/spec/cli.md#ab-schema). The repo
commits the output at ``schema/`` and ``--check`` fails when it has drifted
from ``absicht.models`` — a schema file is a build artifact, never authored.

One file per kind of file a store can hold, named after the store directory
that holds it (``components/`` -> ``components.schema.json``), plus the two
singletons ``system`` and ``marker``. The set is walked from ``Design``'s own
fields rather than hand-listed — the same anti-drift principle as
``absicht.resolve``'s reference walk: ``Design`` is a store folded flat, so
its field names are the store's directory names (docs/tasks/00-conventions.md
pins the two together) and its annotations the models a file in that
directory validates against. A kind added to ``models.py`` gets its schema
file the moment ``Design`` grows its tuple, with no second list to forget.
``Marker`` is named alongside the walk because a repo's ``.absicht`` marker
file is authored in implementing repos, not held by a ``Design``.

Pydantic does the generation; nested records (``Criterion``, ``Unit``, …)
ride along in each parent's ``$defs``, so every file is self-contained. This
module's job is the layout and the one spelling of the bytes: ``json.dumps``
of the model's own ordered mapping — deterministic across runs and across
interpreters, which ``tests/test_schema.py`` holds it to under varying
``PYTHONHASHSEED``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args, get_origin

from absicht.models import Design, Marker, Record

_SUFFIX = ".schema.json"
_MARKER_KIND = "marker"
"""The marker file's kind name: ``.absicht`` is a singleton, so it has no
`Design` field to walk its name from."""


def write_schemas(out: Path) -> tuple[str, ...]:
    """Write every schema file into ``out`` (created when missing).

    Returns the file names written, in the walk's order. Overwriting is the
    point — the models are the truth, the directory is their shadow.
    """
    texts = _schema_texts()
    out.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (out / name).write_text(text, encoding="utf-8")
    return tuple(texts)


def stale_schemas(out: Path) -> tuple[str, ...]:
    """The schema files under ``out`` that disagree with ``absicht.models`` today.

    Stale is three states: a file whose bytes moved, a file the models no
    longer generate, and one they do generate that is missing — an up-to-date
    directory is exactly the generated set. Only ``*.schema.json`` files
    count, so a README kept next to them is not a finding.
    """
    texts = _schema_texts()
    stale = [
        name
        for name, text in texts.items()
        if not (out / name).is_file() or (out / name).read_text(encoding="utf-8") != text
    ]
    if out.is_dir():
        # sorted: glob order is directory order, and this list reaches stdout.
        stale.extend(
            path.name for path in sorted(out.glob(f"*{_SUFFIX}")) if path.name not in texts
        )
    return tuple(stale)


def _schema_texts() -> dict[str, str]:
    """The whole output as ``file name -> text``, in `Design` field order."""
    return {f"{kind}{_SUFFIX}": _dump(model) for kind, model in _file_models().items()}


def _file_models() -> dict[str, type[Record]]:
    """The models a store file can hold, by the store directory that holds it."""
    models = {
        name: model
        for name, field in Design.model_fields.items()
        if (model := _record_of(field.annotation)) is not None
    }
    models[_MARKER_KIND] = Marker
    return models


def _record_of(annotation: object) -> type[Record] | None:
    """The `Record` a `Design` field holds, unwrapped from its tuple.

    The two shapes in `Design` are `System` and `tuple[SomeElement, ...]`;
    anything else (`schema_version`'s int) names no file format.
    """
    if get_origin(annotation) is tuple:
        annotation = get_args(annotation)[0]
    if isinstance(annotation, type) and issubclass(annotation, Record):
        return annotation
    return None


def _dump(model: type[Record]) -> str:
    """One spelling of the serialization, ending in the newline git fixers want."""
    return json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
