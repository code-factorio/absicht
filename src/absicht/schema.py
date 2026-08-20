"""Regenerate the JSON Schema files a store's files validate against.

``ab schema`` writes these so an editor can autocomplete and inline-flag
fields while an element is authored (docs/spec/cli.md#ab-schema). The repo
commits the output at ``schema/`` and ``--check`` fails when it has drifted
from the models — a schema file is a build artifact, never authored.

One file per kind of file a store can hold, named after the store directory
that holds it (``components/`` -> ``components.schema.json``), plus the
three singletons ``design``, ``layout`` and ``marker``. The set comes from
``absicht.codec``'s ``DIRECTORIES`` rather than a list of its own: the
directory layout is part of the on-disk format, so the module that owns the
format owns the map, and a kind added to the store gets its schema file with
no second list to forget.

``codec`` also generates each document's schema, because a file holds more
than its model does — an element's front matter may carry ``relates``, which
the model refuses. Nested records ride along in each parent's ``$defs``, so
every file is self-contained. This module's job is the layout and the one
spelling of the bytes: ``json.dumps`` of the model's own ordered mapping —
deterministic across runs and across interpreters, which
``tests/test_schema.py`` holds it to under varying ``PYTHONHASHSEED``.
"""

from __future__ import annotations

import json
from pathlib import Path

from absicht.codec import DIRECTORIES, document_schema
from absicht.models.design import Design, Record
from absicht.models.layout import Layout
from absicht.models.marker import Marker

_SUFFIX = ".schema.json"

_SINGLETONS: dict[str, type[Record]] = {
    "design": Design,
    "layout": Layout,
    "marker": Marker,
}
"""The files a store holds one of, named beside the walk.

``design.yaml`` and ``layout.yaml`` are singletons of the store; a repo's
``.absicht`` marker is authored in implementing repos and held by no store at
all. None of the three has a directory to take its name from.
"""


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
    """The schema files under ``out`` that disagree with the models today.

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
    """The models a store file can hold, by the file or directory holding it."""
    return {**DIRECTORIES, **_SINGLETONS}


def _dump(model: type[Record]) -> str:
    """One spelling of the serialization, ending in the newline git fixers want."""
    return json.dumps(document_schema(model), indent=2, ensure_ascii=False) + "\n"
