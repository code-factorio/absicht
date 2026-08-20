"""The single place that knows how a record is spelled on disk.

Everything above this layer works with the pydantic models from
`absicht.models`; nothing below it ever sees a `Path` or a YAML document —
which is what keeps the file format swappable later. The format:

- one element per file as YAML front matter between `---` lines, followed by
  the Markdown body verbatim. Every field except the loader-set `source` and
  the never-parsed `body` lives in the header;
- `relates`, in an element's own front matter, holds that element's outgoing
  relationships. The model keeps them in one list on the `Design` so two
  elements can never disagree about a link; the store keeps them beside the
  element that owns them so one edit touches one file. Translating between
  the two is this module's job, and `DIRECTORIES` is the same fact about the
  layout: which `Design` field a store directory holds;
- singletons (`design.yaml`, `layout.yaml`, a repo `.absicht` marker) are
  plain YAML with no front-matter split.

The decisions the format leaves open are made here and pinned in
`tests/test_codec.py`:

- the first `---` pair wins: the file must open with one, and the next bare
  `---` line closes the front matter — a body may itself contain `---` rules;
- prose without front matter is refused rather than read as an empty header:
  `id` and `title` live in the header, so such a file is malformed, not
  minimal;
- the only exception that escapes this module is `CodecError`. The YAML
  parser's and pydantic's own exceptions are translated at the boundary so
  `absicht.load` can turn a bad file into a finding without knowing either
  library's exception shape. `CodecError` splits into `CodecSyntaxError` and
  `CodecValidationError` — the distinction `absicht.check` maps to rule ids —
  while staying one boundary type for every caller that only cares that a
  file failed.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import yaml
from pydantic import ValidationError, create_model

from absicht.models.design import (
    Actor,
    Assumption,
    Behavior,
    Component,
    Constraint,
    DataEntity,
    Decision,
    Design,
    Element,
    ExternalService,
    Goal,
    Interface,
    Library,
    Milestone,
    Note,
    QualityRequirement,
    Question,
    Record,
    Ref,
    Rejection,
    Relationship,
    RelationshipType,
    Requirement,
    Resource,
    Term,
)

_DELIMITER = "---"
"""Front-matter delimiter, as in Jekyll/Hugo. `...` is not accepted."""

_RELATES = "relates"
"""The reserved front-matter key holding an element's outgoing edges."""

DIRECTORIES: dict[str, type[Record]] = {
    "glossary": Term,
    "actors": Actor,
    "goals": Goal,
    "requirements": Requirement,
    "qualities": QualityRequirement,
    "constraints": Constraint,
    "behaviors": Behavior,
    "components": Component,
    "interfaces": Interface,
    "data_entities": DataEntity,
    "resources": Resource,
    "libraries": Library,
    "external_services": ExternalService,
    "assumptions": Assumption,
    "decisions": Decision,
    "questions": Question,
    "rejections": Rejection,
    "milestones": Milestone,
    "notes": Note,
}
"""Store directory -> the model a file in it holds, in `Design` field order.

The directory name is the `Design` field name, which is what lets `load` walk
a store and `resolve` fold the result back with no second mapping. Not
derived from `Design`'s annotations, because `revisions`, `imports` and
`repositories` are tuples too and are authored inline in `design.yaml`.
"""

ASSEMBLED: tuple[str, ...] = (*DIRECTORIES, "relationships")
"""The `Design` fields `design.yaml` never states: the ones the walk builds
out of element files."""


class CodecError(Exception):
    """A record's text is not the format, or its fields do not validate.

    The message is written for the layer above to lift into a finding as-is:
    it names the record type and the offending field, never a stack trace.
    """


class CodecSyntaxError(CodecError):
    """The text does not read as the format at all: YAML the parser refuses,
    a document that is not a mapping, or missing/unterminated front matter."""


class CodecValidationError(CodecError):
    """The text parsed, but the record's fields did not validate."""


class Relates(Record):
    """One outgoing edge, as the element that owns it spells it.

    No `source_id`: the file the edge is written in is the source, and saying
    so twice invites the two to disagree.
    """

    to: Ref
    type: RelationshipType
    description: str | None = None
    technology: str = ""


def dump_element(record: Element | Note, *, relates: Iterable[Relationship] = ()) -> str:
    """Render one front-matter record: the header, then the body verbatim.

    Notes are not elements — they never enter the `Design` — but their files
    are the same shape, so they ride this spelling rather than growing a
    second one. An edge is written back the way it was authored, with the
    source dropped: it is the file it sits in.
    """
    prose = _prose_field(type(record))
    body = str(getattr(record, prose)) if prose else ""
    fields = _authored_fields(record, drop=(prose,) if prose else ())
    outgoing = [
        Relates(
            to=edge.target_id,
            type=edge.type,
            description=edge.description,
            technology=edge.technology,
        ).model_dump(mode="json")
        for edge in relates
    ]
    if outgoing:
        fields[_RELATES] = outgoing
    return f"{_DELIMITER}\n{_dump_yaml(fields)}{_DELIMITER}\n{body}"


def parse_element[R: Record](
    text: str, *, model: type[R], source: str
) -> tuple[R, tuple[Relationship, ...]]:
    """Read one front-matter record and the edges its file owns.

    `source` is stamped from the path the loader read, where the model keeps
    one. Only an `Element` may carry `relates`; on anything else the key
    stays in the mapping and pydantic refuses it, which is the report we want.
    """
    front_matter, body = _split_front_matter(text)
    fields = _load_mapping(front_matter, what="front matter")
    authored = fields.pop(_RELATES, None) if issubclass(model, Element) else None
    if "source" in model.model_fields:
        fields["source"] = source
    if (prose := _prose_field(model)) is not None:
        fields[prose] = body
    record = _build(model, fields)
    return record, _edges(str(getattr(record, "id", "")), authored)


def _prose_field(model: type[Record]) -> str | None:
    """Which field the file's Markdown lands in.

    An element calls it `body` and a note calls it `text`, because a note is
    nothing but its text. A singleton has neither and its file is all header.
    """
    for name in ("body", "text"):
        if name in model.model_fields:
            return name
    return None


def dump_singleton(record: Record) -> str:
    """Render a singleton (`layout.yaml`, a `.absicht` marker) as plain YAML."""
    return _dump_yaml(_authored_fields(record))


def dump_design(design: Design) -> str:
    """Render `design.yaml`: the design's own header, without the store.

    Everything in `ASSEMBLED` is many files on disk, so writing it here too
    would be a second copy that drifts on the first edit.
    """
    return _dump_yaml(_authored_fields(design, drop=ASSEMBLED))


def parse_singleton[R: Record](text: str, *, model: type[R]) -> R:
    """Read a singleton: plain YAML, no front-matter split."""
    return _build(model, _load_mapping(text, what=model.__name__))


def document_schema(model: type[Record]) -> dict[str, object]:
    """The JSON Schema of one store file: the model, plus what the format adds.

    An element's file may carry `relates`, which the model itself forbids —
    an assembled edge lives on the `Design`. An editor validating the file has
    to be told about the key here, or every authored relationship reads as an
    error.
    """
    if not issubclass(model, Element):
        return model.model_json_schema()
    document = create_model(model.__name__, __base__=model, relates=(tuple[Relates, ...], ()))
    return document.model_json_schema()


def _edges(source_id: str, authored: object) -> tuple[Relationship, ...]:
    """Lift an element's authored `relates` block into whole relationships."""
    if authored is None:
        return ()
    if not isinstance(authored, list):
        raise CodecSyntaxError(f"{_RELATES} must be a list, not {type(authored).__name__}")
    return tuple(
        Relationship(
            source_id=source_id,
            target_id=edge.to,
            type=edge.type,
            description=edge.description,
            technology=edge.technology,
        )
        for edge in (_build(Relates, _mapping(item)) for item in authored)
    )


def _mapping(item: object) -> dict[str, object]:
    if not isinstance(item, dict):
        raise CodecSyntaxError(f"a {_RELATES} entry must be a mapping, not {type(item).__name__}")
    return cast("dict[str, object]", item)


def _authored_fields(record: Record, *, drop: Iterable[str] = ()) -> dict[str, object]:
    """The fields a human writes, in the model's declaration order.

    `model_dump` walks fields in declaration order, so equal records always
    dump to equal text and diffs stay small. `mode="json"` keeps the values
    plain (enums and dates as strings), which is all YAML can say anyway.
    """
    dumped: dict[str, object] = record.model_dump(mode="json", exclude={"source", *drop})
    return dumped


def _dump_yaml(fields: dict[str, object]) -> str:
    """One spelling of the dump options, so the dump paths cannot drift."""
    return yaml.safe_dump(fields, sort_keys=False, allow_unicode=True)


def _split_front_matter(text: str) -> tuple[str, str]:
    """Split a file into its front matter and its verbatim body."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _DELIMITER:
        raise CodecSyntaxError(f"no front matter: the file must start with a {_DELIMITER!r} line")
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _DELIMITER:
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise CodecSyntaxError(f"unterminated front matter: no closing {_DELIMITER!r} line")


def _load_mapping(text: str, *, what: str) -> dict[str, object]:
    """Parse YAML that must be a mapping; an empty document reads as empty."""
    try:
        data: object = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CodecSyntaxError(f"invalid YAML in {what}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise CodecSyntaxError(f"{what} must be a YAML mapping, not {type(data).__name__}")
    return cast("dict[str, object]", data)


def _build[R: Record](model: type[R], fields: dict[str, object]) -> R:
    """Validate a field mapping, translating pydantic's exception at the boundary."""
    try:
        return model.model_validate(fields)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '(root)'}: {error['msg']}"
            for error in exc.errors(include_url=False)
        )
        raise CodecValidationError(f"{model.__name__} validation failed: {problems}") from exc
