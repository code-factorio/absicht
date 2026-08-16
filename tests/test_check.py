"""``absicht.check``'s schema layer: every ``LoadError`` becomes one finding.

The schema layer is the one with the least new logic — pydantic and the codec
already did the validating inside ``load``. What these tests pin is the
translation, and the decisions it rests on:

- one ``LoadError`` reason maps to exactly one rule id at error severity: a
  file that does not parse is never advisory, and the rule id must say *what
  kind* of schema problem it was, because that is what ``--explain`` answers;
- a validation finding names the offending field — or, for a whole-record
  validator, the thing it rejected — since ``Finding.message`` is all an
  agent fixing the store gets to read;
- the shared fixtures stay the safety net: ``broken`` reports exactly its two
  deliberately unparseable files and nothing else (its other defects are the
  integrity and policy layers' to judge), while ``clean`` and ``brownfield``
  parse without a word.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from absicht.check import schema_findings

from absicht.findings import Severity
from absicht.load import LoadedStore, LoadError, LoadErrorReason, load_store

FIXTURES = Path(__file__).parent / "fixtures" / "systems"

# The translation table, restated per reason: a reason added to the enum
# without a rule (there or here) fails loudly rather than reporting
# "something is wrong" under a borrowed id.
RULE_BY_REASON = {
    LoadErrorReason.SYNTAX: "schema/yaml-syntax",
    LoadErrorReason.VALIDATION: "schema/validation",
    LoadErrorReason.MISSING_SYSTEM: "schema/system-missing",
    LoadErrorReason.IO: "schema/unreadable-file",
}


@pytest.mark.parametrize("reason", list(LoadErrorReason))
def test_every_load_error_reason_becomes_its_rule_at_error_severity(
    reason: LoadErrorReason,
) -> None:
    loaded = LoadedStore(
        system=None,
        errors=(LoadError(path="components/x.md", message="what went wrong", reason=reason)),
    )

    (only,) = schema_findings(loaded)

    assert only.rule_id == RULE_BY_REASON[reason]
    assert only.severity is Severity.ERROR
    assert only.source == "components/x.md"
    assert only.message == "what went wrong"


def test_the_broken_store_reports_exactly_its_two_parse_failures() -> None:
    """`06-fixtures.md` puts one clearly-named file per failure family in
    `broken/`; only two fail at the schema layer. The rest parse on purpose —
    a dangling ref, a `contains` cycle and the policy cases are findings the
    integrity and policy layers own, not files the loader refused."""

    by_path = {found.source: found for found in schema_findings(load_store(FIXTURES / "broken"))}

    assert set(by_path) == {"requirements/garbage.md", "stories/bad-anchor.md"}

    garbage = by_path["requirements/garbage.md"]
    assert garbage.rule_id == "schema/yaml-syntax"
    assert "invalid YAML" in garbage.message

    bad_anchor = by_path["stories/bad-anchor.md"]
    assert bad_anchor.rule_id == "schema/validation"
    # A whole-record validator reports at `(root)`, so the message itself has
    # to name what it rejected: the criterion, and the story it should anchor to.
    assert (
        "criterion 'story:other-story#ac-1' is not anchored to 'story:bad-anchor'"
        in bad_anchor.message
    )


@pytest.mark.parametrize("name", ["clean", "brownfield"])
def test_stores_that_parse_have_no_schema_findings(name: str) -> None:
    """`brownfield` has plenty for the policy layer to say later; none of it
    is a parse failure, and the schema layer must not reach for it."""

    assert schema_findings(load_store(FIXTURES / name)) == ()


def test_a_field_violation_names_the_field_in_the_message(tmp_path: Path) -> None:
    """The spec's own confirmation, written as a test: a pydantic
    `ValidationError`'s message must survive the `CodecError` → `Finding`
    chain naming the offending field, not just "validation failed"."""

    _write(tmp_path, "system.yaml", "id: system:tiny\ntitle: Tiny\n")
    _write(tmp_path, "components/bad-id.md", "---\nid: Not a Ref\ntitle: X\n---\n")

    (only,) = schema_findings(load_store(tmp_path))

    assert only.rule_id == "schema/validation"
    assert "id: String should match pattern" in only.message


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
