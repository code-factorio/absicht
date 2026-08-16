"""The single place that knows how a record is spelled on disk.

Everything above this layer works with the pydantic models from
`absicht.models`; nothing below it ever sees a `Path` or a YAML document —
which is what keeps the file format swappable later. The format itself is
pinned in `docs/tasks/00-conventions.md`: one element per file as YAML front
matter (every field except the loader-set `source` and the never-parsed
`body`) between `---` lines, followed by the Markdown body verbatim;
singletons (`system.yaml`, a repo `.absicht` marker) are plain YAML.

The decisions that document leaves open are made here and pinned in
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

from typing import cast

import yaml
from pydantic import ValidationError

from absicht.models import Element, Record

_DELIMITER = "---"
"""Front-matter delimiter, as in Jekyll/Hugo. `...` is not accepted."""


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


def dump_element(element: Element) -> str:
    """Render one element: front matter, then the body verbatim."""
    header = _dump_yaml(_authored_fields(element))
    return f"{_DELIMITER}\n{header}{_DELIMITER}\n{element.body}"


def parse_element[E: Element](text: str, *, model: type[E], source: str) -> E:
    """Read one element, stamping `source` from the path the loader is reading."""
    front_matter, body = _split_front_matter(text)
    fields = _load_mapping(front_matter, what="front matter")
    fields["source"] = source
    fields["body"] = body
    return _build(model, fields)


def dump_singleton(record: Record) -> str:
    """Render a singleton (`system.yaml`, a `.absicht` marker) as plain YAML."""
    return _dump_yaml(_authored_fields(record))


def parse_singleton[R: Record](text: str, *, model: type[R]) -> R:
    """Read a singleton: plain YAML, no front-matter split."""
    return _build(model, _load_mapping(text, what=model.__name__))


def _authored_fields(record: Record) -> dict[str, object]:
    """The fields a human writes, in the model's declaration order.

    `model_dump` walks fields in declaration order, so equal records always
    dump to equal text and diffs stay small. `mode="json"` keeps the values
    plain (enums and dates as strings), which is all YAML can say anyway.
    """
    return record.model_dump(mode="json", exclude={"source", "body"})


def _dump_yaml(fields: dict[str, object]) -> str:
    """One spelling of the dump options, so the two dump paths cannot drift."""
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
