"""``absicht.check``: the schema layer and the integrity layer.

The schema layer is the one with the least new logic — pydantic and the codec
already did the validating inside ``load``. What its tests pin is the
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

The integrity layer reads the resolved artifact instead of the load errors:

- a dangling ref is one finding naming the source element, the field and the
  missing target, enumerated over ``iter_references`` — the same walk
  ``Index`` is built from, so a ref-typed field added to a model is checked
  without this module learning about it. ``System.externals`` needs no
  multi-repo rule of its own: it is a plain ref-typed field, the sweep
  covers it, and the finding lands on the system element.
- a cycle in ``contains`` or ``depends_on`` is one finding per distinct
  cycle, not per edge — two disjoint loops are two findings, however many
  edges they span, and each relation is its own directed graph.
- criteria anchoring, the spec's third integrity line, cannot be violated
  here: ``Story``'s own validator rejects a misanchored criterion at parse
  time. The rule id stays registered, marked handled upstream, so
  ``--explain`` still answers for it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from absicht.check import integrity_findings, schema_findings
from absicht.findings import RULES, Finding, Severity
from absicht.load import LoadedStore, LoadError, LoadErrorReason, load_store
from absicht.models import Component, Design, Milestone, System
from absicht.resolve import Index, resolve

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
        errors=(LoadError(path="components/x.md", message="what went wrong", reason=reason),),
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


# --- the integrity layer ----------------------------------------------------


def _integrity(name: str) -> tuple[Finding, ...]:
    """Run `integrity_findings` over one fixture store, resolved and indexed."""
    design = resolve(load_store(FIXTURES / name))
    return integrity_findings(design, Index.from_design(design))


def test_broken_reports_exactly_its_dangling_ref_and_its_contains_cycle() -> None:
    """`broken/`'s two integrity defects, per `06-fixtures.md`: `dangling.md`
    points at a ghost through `contains`, and `loop-a`/`loop-b` contain each
    other — one cycle, one finding. The policy cases (the unowned unknown, the
    one-way decision without rationale, the expired external) parse and resolve
    fine, and the two files that fail to load never reach a `Design` at all."""

    (dangling, cycle) = _integrity("broken")

    assert dangling.rule_id == "integrity/dangling-ref"
    assert dangling.severity is Severity.ERROR
    assert dangling.ref == "component:dangling"
    assert dangling.source == "components/dangling.md"
    assert "component:dangling" in dangling.message
    assert "contains" in dangling.message
    assert "component:ghost" in dangling.message

    assert cycle.rule_id == "integrity/cycle"
    assert cycle.severity is Severity.ERROR
    assert "contains" in cycle.message
    assert "component:loop-a" in cycle.message
    assert "component:loop-b" in cycle.message


@pytest.mark.parametrize("name", ["clean", "brownfield"])
def test_stores_whose_refs_resolve_have_no_integrity_findings(name: str) -> None:
    """`clean/` is internally consistent by construction; `brownfield/`'s
    problems (orphans, the unowned unknown) are policy's to judge. Neither
    dangles a ref nor cycles a relation."""

    assert _integrity(name) == ()


def test_disjoint_contains_cycles_are_one_finding_each_not_one_per_edge() -> None:
    """A two-node cycle and a three-node cycle in the same design: two
    findings, one per distinct cycle. Five edges produce two lines, not five —
    the reader is told what is wrong, not everything that is part of it."""

    design = Design(
        system=System(id="system:tiny", title="Tiny"),
        components=(
            Component(id="component:two-a", title="Two A", contains=("component:two-b",)),
            Component(id="component:two-b", title="Two B", contains=("component:two-a",)),
            Component(id="component:three-a", title="Three A", contains=("component:three-b",)),
            Component(id="component:three-b", title="Three B", contains=("component:three-c",)),
            Component(id="component:three-c", title="Three C", contains=("component:three-a",)),
        ),
    )
    all_ids = (
        "component:two-a",
        "component:two-b",
        "component:three-a",
        "component:three-b",
        "component:three-c",
    )

    findings = integrity_findings(design, Index.from_design(design))

    assert [f.rule_id for f in findings] == ["integrity/cycle", "integrity/cycle"]
    # Which members each finding names — sorted, so the assertion does not
    # depend on which cycle graphlib happens to report first.
    members = sorted(sorted(ref for ref in all_ids if ref in f.message) for f in findings)
    assert members == [
        ["component:three-a", "component:three-b", "component:three-c"],
        ["component:two-a", "component:two-b"],
    ]


def test_a_milestone_depends_on_cycle_is_its_own_graphs_problem() -> None:
    """`contains` and `depends_on` are checked as separate directed graphs: a
    milestone cycle is caught by the same rule even when no component nests
    wrongly, because 'before' going undefined is the same failure."""

    design = Design(
        system=System(id="system:tiny", title="Tiny"),
        milestones=(
            Milestone(id="milestone:m1", title="M1", depends_on=("milestone:m2",)),
            Milestone(id="milestone:m2", title="M2", depends_on=("milestone:m1",)),
        ),
    )

    (only,) = integrity_findings(design, Index.from_design(design))

    assert only.rule_id == "integrity/cycle"
    assert "depends_on" in only.message
    assert "milestone:m1" in only.message
    assert "milestone:m2" in only.message


def test_a_dangling_external_on_the_system_is_the_generic_dangling_ref() -> None:
    """The spec's multi-repo sanity line resolves to "no separate rule":
    `System.externals` is a plain ref-typed field, the generic sweep covers
    it, and the finding lands on the system element. Its `source` is None —
    the singleton `system.yaml` carries no per-element path."""

    design = Design(
        system=System(id="system:tiny", title="Tiny", externals=("external:ghost",)),
    )

    (only,) = integrity_findings(design, Index.from_design(design))

    assert only.rule_id == "integrity/dangling-ref"
    assert only.ref == "system:tiny"
    assert only.source is None
    assert "externals" in only.message
    assert "external:ghost" in only.message


def test_criteria_anchoring_is_registered_as_handled_upstream() -> None:
    """The spec's third integrity line is enforced at the schema layer: a
    misanchored criterion cannot survive `load` (pinned above, by
    `test_the_broken_store_reports_exactly_its_two_parse_failures`). Its id
    stays in the catalog — marked handled upstream — so `--explain` answers
    for the spec line rather than silently dropping it."""

    assert "integrity/criteria-anchored" in RULES


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
