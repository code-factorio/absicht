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
- the shared fixtures stay the safety net: ``broken`` reports exactly its
  three deliberately unparseable files and nothing else (its other defects
  are the integrity and policy layers' to judge), while ``clean`` and
  ``brownfield`` parse without a word.

The integrity layer reads the resolved artifact instead of the load errors:

- a dangling ref is one finding naming the source element, the field and the
  missing target, enumerated over ``iter_references`` — the same walk
  ``Index`` is built from, so a ref-typed field added to a model is checked
  without this module learning about it. ``System.externals`` needs no
  multi-repo rule of its own: it is a plain ref-typed field, the sweep
  covers it, and the finding lands on the system element. An observation's
  ``at`` joins the sweep the same way, attributed to the behavior that
  carries it — the generic walk covering it is why the addendum's
  observation-at rule only needs to police *kind*, not existence.
- a cycle in ``contains`` or ``depends_on`` is one finding per distinct
  cycle, not per edge — two disjoint loops are two findings, however many
  edges they span, and each relation is its own directed graph.
- criteria anchoring, the spec's third integrity line, cannot be violated
  here: ``Story``'s own validator rejects a misanchored criterion at parse
  time. The rule id stays registered, marked handled upstream, so
  ``--explain`` still answers for it.

The policy layer is the judgement layer, and its severities are the contract:

- an ``unknown`` with no owner and a ``one_way`` decision with no rationale
  are errors — the spec's own "needs" wording — while an unrealized
  requirement and an expired external assumption are warnings:
  incomplete-but-honest and stale-but-routine are brownfield's legitimate
  states, not breakage. ``observed`` alone is never a finding.
- the clock is injected: ``today`` is a parameter of the run, never read
  inside a rule, so an expiry is "past as of when the caller says", and the
  tests never depend on the real date.

The model addendum grows all three layers, and its rule table — ids,
severities, which rules are subsumed by existing machinery — is pinned in
``docs/tasks/50-addendum-conventions.md``; these tests implement that table
rather than re-deriving it:

- integrity: a seam referencing a resource, an observation whose ``at`` is
  the wrong kind (existence is already the generic dangling-ref sweep's, so
  the addendum's unresolvable ids stay registered but never emitted), and
  the two new cycle walks — composition through observations' ``at``, and
  supersession — joining the same ``_cycles`` machinery: one finding per
  distinct loop, self-supersession the length-1 case of the same id.
- policy: a behavior with no observations is an error whatever its
  lifecycle; a requirement no *active* behavior realizes is the addendum's
  one warning (a superseded behavior stopped being true, so realizing with
  one is not realizing); a milestone selecting a superseded behavior is a
  contradiction and an error.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from absicht.check import integrity_findings, policy_findings, schema_findings
from absicht.findings import RULES, Finding, Severity
from absicht.load import LoadedStore, LoadError, LoadErrorReason, load_store
from absicht.models import (
    Behavior,
    Component,
    Decision,
    Design,
    External,
    ExternalKind,
    Lifecycle,
    Milestone,
    Observation,
    Question,
    Requirement,
    Resource,
    ResourceKind,
    Reversibility,
    Seam,
    SeamStyle,
    State,
    System,
)
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


def test_the_broken_store_reports_exactly_its_three_parse_failures() -> None:
    """`06-fixtures.md` puts one clearly-named file per failure family in
    `broken/`; only three fail at the schema layer. The rest parse on purpose —
    a dangling ref, a `contains` cycle and the policy cases are findings the
    integrity and policy layers own, not files the loader refused."""

    by_path = {found.source: found for found in schema_findings(load_store(FIXTURES / "broken"))}

    assert set(by_path) == {
        "requirements/garbage.md",
        "stories/bad-anchor.md",
        "behaviors/bad-timing.md",
    }

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

    bad_timing = by_path["behaviors/bad-timing.md"]
    assert bad_timing.rule_id == "schema/validation"
    assert "`must_not` means at no point: omit `timing`" in bad_timing.message


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


def test_broken_reports_exactly_its_integrity_findings() -> None:
    """The whole integrity report over `broken/`, in the order the layer yields
    it: the pre-addendum trio (two dangling refs, the `contains` cycle) then
    one finding per addendum rule, each on its own clearly-named fixture file —
    so `ab check --rule X` points at exactly the case that trips it."""

    assert [found.rule_id for found in _integrity("broken")] == [
        "integrity/dangling-ref",
        "integrity/dangling-ref",
        "integrity/cycle",
        "integrity/seam-references-resource",
        "integrity/observation-at-wrong-kind",
        "integrity/composition-cycle",
        "integrity/supersession-cycle",
    ]


def test_broken_reports_exactly_its_dangling_refs_and_its_contains_cycle() -> None:
    """`broken/`'s pre-addendum integrity findings, still exactly these three:
    `dangling.md` points at a ghost through `contains`, the dangling
    observation's `at` names a resource nothing defines, and `loop-a`/`loop-b`
    contain each other — one cycle, one finding. The observation finding is
    the generic sweep covering the addendum's nested records: it names the
    behavior that carries the observation, the `at` field and the missing
    target, with no rule of its own. Selected by rule id from the report the
    test above inventories; the addendum's own findings are pinned below."""

    dangling, observation = (
        found for found in _integrity("broken") if found.rule_id == "integrity/dangling-ref"
    )

    assert dangling.severity is Severity.ERROR
    assert dangling.ref == "component:dangling"
    assert dangling.source == "components/dangling.md"
    assert "component:dangling" in dangling.message
    assert "contains" in dangling.message
    assert "component:ghost" in dangling.message

    assert observation.severity is Severity.ERROR
    assert observation.ref == "behavior:dangling-observation"
    assert observation.source == "behaviors/dangling-observation.md"
    # Pinned exactly, like the cycle below: the finding names the behavior,
    # the field and the missing target, and that text is user-facing.
    assert observation.message == (
        "behavior:dangling-observation's at points at resource:ghost-store, "
        "which no element in the store defines"
    )

    (cycle,) = (found for found in _integrity("broken") if found.rule_id == "integrity/cycle")

    assert cycle.severity is Severity.ERROR
    # Pinned exactly, not as substrings: the finding text is user-facing and
    # must stay deterministic — same store, same line, closed path included.
    assert cycle.message == (
        "contains edges form a cycle: component:loop-a -> component:loop-b -> component:loop-a"
    )


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
    assert only.message == (
        "depends_on edges form a cycle: milestone:m1 -> milestone:m2 -> milestone:m1"
    )


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


# --- the addendum's integrity rules -------------------------------------------


def _broken_integrity(rule_id: str) -> Finding:
    """The one finding `broken/` carries under an addendum rule — the fixture
    holds exactly one clearly-named file per rule, so a rule with no finding
    here is a fixture that lost its trip wire, not a quiet rule."""
    matches = [found for found in _integrity("broken") if found.rule_id == rule_id]
    (only,) = matches
    return only


def test_a_seam_referencing_a_resource_is_an_error_naming_the_field() -> None:
    """`broken/`'s `legacy-cache` seam resolves — the resource exists — but the
    kind it points at is the defect (§1.4): the finding names the seam, the
    field and the resource, so the fix (a dependency, not a contract) has a
    place to land. `clean/`'s `order-events` seam, provider and consumers all
    components, is the adjacent case that says nothing."""

    only = _broken_integrity("integrity/seam-references-resource")

    assert only.severity is Severity.ERROR
    assert only.ref == "seam:legacy-cache"
    assert only.source == "seams/legacy-cache.md"
    # Pinned exactly: the message is user-facing and must stay deterministic.
    assert only.message == (
        "seam:legacy-cache's provider names resource:audit-store: a seam is a contract "
        "between components, and a component's relationship to a resource is a dependency"
    )


def test_a_seam_may_not_name_a_resource_through_any_of_its_ref_fields() -> None:
    """The rule's reach beyond the fixture's `provider` case: a resource as a
    consumer or carried across is the same dependency wearing a contract, one
    finding per offending ref with the field it came through named — the
    reach mutation testing asked for, since `provider` was all the fixture
    pinned."""

    design = Design(
        system=System(id="system:tiny", title="Tiny"),
        components=(Component(id="component:api", title="API"),),
        # Both resources exist, like the fixture's: the refs resolve, and the
        # defect is the kind they point at through the seam — not a dangle.
        resources=(
            Resource(
                id="resource:cache",
                title="Cache",
                resource_kind=ResourceKind.STORE,
                technology="Redis",
            ),
            Resource(
                id="resource:store",
                title="Store",
                resource_kind=ResourceKind.STORE,
                technology="PostgreSQL",
            ),
        ),
        seams=(
            Seam(
                id="seam:leaky",
                title="Leaky",
                style=SeamStyle.SCHEMA,
                consumers=("component:api", "resource:cache"),
                carries=("resource:store",),
            ),
        ),
    )

    findings = integrity_findings(design, Index.from_design(design))

    assert [(found.rule_id, found.message) for found in findings] == [
        (
            "integrity/seam-references-resource",
            "seam:leaky's consumers names resource:cache: a seam is a contract between "
            "components, and a component's relationship to a resource is a dependency",
        ),
        (
            "integrity/seam-references-resource",
            "seam:leaky's carries names resource:store: a seam is a contract between "
            "components, and a component's relationship to a resource is a dependency",
        ),
    ]


def test_an_observation_at_the_wrong_kind_is_an_error_naming_the_observation() -> None:
    """`at` pointing at a requirement, decision or question resolves — the
    target exists — and is still wrong: what an observation may be about is a
    component, a resource, a seam or another behavior. The finding names the
    observation (its id embeds the behavior) and the target."""

    only = _broken_integrity("integrity/observation-at-wrong-kind")

    assert only.severity is Severity.ERROR
    assert only.ref == "behavior:observation-at-decision"
    assert only.source == "behaviors/observation-at-decision.md"
    assert only.message == (
        "behavior:observation-at-decision#obs-1's at points at decision:one-way-no-why; "
        "an observation may point at a component, a resource, a seam or another behavior"
    )


def test_an_observation_at_a_note_says_why_that_target_can_never_resolve() -> None:
    """The note half of the wrong-kind rule, which no fixture holds (a note is
    not an element, so a fixture file pointing at one would dangle as well):
    the message folds in why a note is special — it can never resolve, not
    merely does not. The same design also dangles, which is the generic
    sweep's finding, not this rule's."""

    design = Design(
        system=System(id="system:tiny", title="Tiny"),
        behaviors=(
            Behavior(
                id="behavior:watching",
                title="Watching",
                trigger="Something is watched.",
                observations=(
                    Observation(
                        id="behavior:watching#obs-1",
                        statement="A note is pointed at",
                        at="note:abc123",
                    ),
                ),
            ),
        ),
    )

    findings = integrity_findings(design, Index.from_design(design))

    assert [found.rule_id for found in findings] == [
        "integrity/dangling-ref",
        "integrity/observation-at-wrong-kind",
    ]
    assert findings[1].message == (
        "behavior:watching#obs-1's at points at note:abc123; a note is not an element "
        "and can never resolve — an observation may point at a component, a resource, "
        "a seam or another behavior"
    )


def test_an_allowed_observation_does_not_stop_the_wrong_kind_walk() -> None:
    """One behavior, two observations — the first points at a component
    (allowed), the second at a question (forbidden): the walk reads every
    observation a behavior carries, not just the first. The cheap failure
    this pins against — skipping to the next behavior on the first allowed
    one — is the survivor mutation testing surfaced."""
    design = Design(
        system=System(id="system:tiny", title="Tiny"),
        components=(Component(id="component:api", title="API"),),
        questions=(Question(id="question:why", title="Why"),),
        behaviors=(
            Behavior(
                id="behavior:mixed",
                title="Mixed",
                trigger="A flow runs.",
                observations=(
                    Observation(id="behavior:mixed#obs-1", statement="Fine", at="component:api"),
                    Observation(id="behavior:mixed#obs-2", statement="Not fine", at="question:why"),
                ),
            ),
        ),
    )

    (only,) = integrity_findings(design, Index.from_design(design))

    assert only.rule_id == "integrity/observation-at-wrong-kind"
    assert only.message == (
        "behavior:mixed#obs-2's at points at question:why; an observation may point at "
        "a component, a resource, a seam or another behavior"
    )


def test_a_composition_cycle_is_one_finding_for_the_one_loop() -> None:
    """`compose-loop-a` and `compose-loop-b` assert each other's occurrence:
    one loop, one finding, the closed path named — the same shape as
    `integrity/cycle`, because it is the same failure: a cycle leaves "what
    causes what" undefined. `clean/`'s `order-placed-v2` composing the
    superseded `order-placed` is the adjacent acyclic case."""

    only = _broken_integrity("integrity/composition-cycle")

    assert only.severity is Severity.ERROR
    assert only.message == (
        "composition edges form a cycle: "
        "behavior:compose-loop-a -> behavior:compose-loop-b -> behavior:compose-loop-a"
    )


def test_a_supersession_cycle_is_one_finding_for_the_one_loop() -> None:
    """`supersede-a` and `supersede-b` replace each other: one loop, one
    finding. `clean/`'s `order-placed-v2` superseding `order-placed` is the
    adjacent acyclic case."""

    only = _broken_integrity("integrity/supersession-cycle")

    assert only.severity is Severity.ERROR
    assert only.message == (
        "supersession edges form a cycle: "
        "behavior:supersede-a -> behavior:supersede-b -> behavior:supersede-a"
    )


def test_self_supersession_is_the_length_one_case_of_the_same_rule() -> None:
    """A behavior superseding itself is the degenerate loop, not its own rule
    id: the pinned table gives supersession one id, and "which behavior is
    current" has no answer either way. No fixture holds it — the cycle pair
    already trips the rule — so this is the one in-design case."""

    design = Design(
        system=System(id="system:tiny", title="Tiny"),
        components=(Component(id="component:api", title="API"),),
        behaviors=(
            Behavior(
                id="behavior:self",
                title="Self",
                trigger="A behavior replaces itself.",
                supersedes=("behavior:self",),
                observations=(
                    Observation(
                        id="behavior:self#obs-1",
                        statement="Something is observable",
                        at="component:api",
                    ),
                ),
            ),
        ),
    )

    (only,) = integrity_findings(design, Index.from_design(design))

    assert only.rule_id == "integrity/supersession-cycle"
    assert only.message == "supersession edges form a cycle: behavior:self -> behavior:self"


# --- the policy layer --------------------------------------------------------


def _policy(name: str, *, today: date) -> tuple[Finding, ...]:
    """Run `policy_findings` over one fixture store, resolved and indexed.

    `today` is injected, never read from the clock: the expiry rule is
    relative to "now", and a test that depends on the real date breaks the day
    after it was written.
    """
    design = resolve(load_store(FIXTURES / name))
    return policy_findings(design, Index.from_design(design), today=today)


def test_brownfield_reports_exactly_its_policy_findings() -> None:
    """`brownfield/` is the honest reading of a legacy system, and the negative
    case this layer must not get wrong: every element but one is `observed`,
    and `observed` alone is never a finding — unexplained is that store's
    honest default, not a violation. The real gaps are `requirement:audit-trail`
    (unknown and unowned — and unrealized twice over: no component realizes it
    and no behavior does either, the addendum's second warning landing beside
    the pre-addendum one) and, since the gaps task grew the fixture,
    `external:payment-api`, whose assumptions lapsed in the past. The two
    questions and the milestone are owned, so the unknown-owner rule still
    fires exactly once."""

    (unowned, unrealized, expired, unbehaviored) = _policy("brownfield", today=date(2026, 8, 16))

    assert unowned.rule_id == "policy/unknown-needs-owner"
    assert unowned.severity is Severity.ERROR
    assert unowned.ref == "requirement:audit-trail"
    assert unowned.source == "requirements/audit-trail.md"
    assert unowned.message == "requirement:audit-trail is unknown and has no owner"

    assert unrealized.rule_id == "policy/requirement-needs-realizer"
    assert unrealized.severity is Severity.WARN
    assert unrealized.ref == "requirement:audit-trail"
    assert unrealized.source == "requirements/audit-trail.md"
    assert unrealized.message == "requirement:audit-trail is realized by no component"

    assert expired.rule_id == "policy/external-assumptions-expired"
    assert expired.severity is Severity.WARN
    assert expired.ref == "external:payment-api"
    assert expired.source == "externals/payment-api.md"
    assert expired.message == (
        "external:payment-api's assumptions expired on 2026-01-01 — re-check before trusting"
    )

    assert unbehaviored.rule_id == "policy/requirement-needs-behavior"
    assert unbehaviored.severity is Severity.WARN
    assert unbehaviored.ref == "requirement:audit-trail"
    assert unbehaviored.source == "requirements/audit-trail.md"
    assert unbehaviored.message == "requirement:audit-trail is realized by no active behavior"


def test_clean_has_no_policy_findings() -> None:
    """`clean/` is complete by construction — every requirement realized by a
    component and by an active behavior, every behavior carrying
    observations, its one decision `costly` (not `one_way`) with a real
    rationale body, no externals to expire — so the judgement layer has
    nothing to say at any severity, the addendum's warning included."""

    assert _policy("clean", today=date(2026, 8, 16)) == ()


def test_broken_reports_exactly_its_policy_defects() -> None:
    """One finding per deliberately broken policy case in `broken/` — the
    unowned unknown, the rationale-less `one_way` decision, the expired
    external, and the addendum's three: the behavior with no observations,
    the requirement no behavior realizes (the one warning), and the milestone
    selecting superseded work — and nothing else: the files the schema layer
    refused never reach the `Design`, and the integrity defects are not
    policy's to judge. The clock is fixed after the fixture's `expires_on`
    (2026-01-10): the date on disk stays put while "today" moves."""

    (unowned, bare, expired, unobservable, unbehaviored, superseded) = _policy(
        "broken", today=date(2026, 8, 16)
    )

    assert (unowned.rule_id, bare.rule_id, expired.rule_id) == (
        "policy/unknown-needs-owner",
        "policy/one-way-needs-rationale",
        "policy/external-assumptions-expired",
    )
    assert (unowned.severity, bare.severity, expired.severity) == (
        Severity.ERROR,
        Severity.ERROR,
        Severity.WARN,
    )
    assert unowned.ref == "question:unowned-unknown"
    assert unowned.source == "questions/unowned-unknown.md"
    assert bare.ref == "decision:one-way-no-why"
    assert bare.source == "decisions/one-way-no-why.md"
    assert expired.ref == "external:expired"
    assert expired.source == "externals/expired.md"
    assert "2026-01-10" in expired.message

    assert unobservable.rule_id == "policy/behavior-needs-observations"
    assert unobservable.severity is Severity.ERROR
    assert unobservable.ref == "behavior:no-observations"
    assert unobservable.source == "behaviors/no-observations.md"
    assert unobservable.message == "behavior:no-observations has no observations"

    assert unbehaviored.rule_id == "policy/requirement-needs-behavior"
    assert unbehaviored.severity is Severity.WARN
    assert unbehaviored.ref == "requirement:no-behavior"
    assert unbehaviored.source == "requirements/no-behavior.md"
    assert unbehaviored.message == "requirement:no-behavior is realized by no active behavior"

    assert superseded.rule_id == "policy/superseded-in-must-satisfy"
    assert superseded.severity is Severity.ERROR
    assert superseded.ref == "milestone:superseded-slice"
    assert superseded.source == "milestones/superseded-slice.md"
    assert superseded.message == (
        "milestone:superseded-slice's includes names behavior:superseded-flow, "
        "which is superseded and stopped being must-satisfy input"
    )


@pytest.mark.parametrize(
    ("today", "expired"),
    [
        (date(2026, 1, 9), False),  # before the expiry: still within what was verified
        (date(2026, 1, 10), False),  # the expiry day itself is not yet "in the past"
        (date(2026, 1, 11), True),  # the day after: re-check before trusting
    ],
)
def test_an_external_expires_only_once_today_is_past_it(today: date, expired: bool) -> None:
    """Both directions of the injected clock, boundary included: `expires_on`
    means "after this, re-check" (`models.py`), so the finding fires strictly
    after the date, never on it. An external with no `expires_on` never fires —
    no expiry was promised, so none can have lapsed. States are `specified` so
    the unknown-owner rule, which this test is not about, stays quiet."""

    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED),
        externals=(
            External(
                id="external:bank",
                title="Bank API",
                state=State.SPECIFIED,
                external_kind=ExternalKind.SERVICE,
                expires_on=date(2026, 1, 10),
            ),
            External(
                id="external:clock",
                title="NTP",
                state=State.SPECIFIED,
                external_kind=ExternalKind.SERVICE,
            ),
        ),
    )

    findings = policy_findings(design, Index.from_design(design), today=today)

    if expired:
        (only,) = findings
        assert only.rule_id == "policy/external-assumptions-expired"
        assert only.severity is Severity.WARN
        assert only.ref == "external:bank"
        assert only.message == (
            "external:bank's assumptions expired on 2026-01-10 — re-check before trusting"
        )
    else:
        assert findings == ()


def test_a_one_way_decision_needs_a_real_rationale_body() -> None:
    """The fixture covers the empty body; this pins the rest of the rule's
    reach: whitespace-only prose is no rationale (an ADR whose argument is
    blank lines), a `one_way` decision that does argue its case is fine, and a
    rationale-less decision that is `cheap` to revisit is fine too — the rule
    is about reversibility, not about bodies for their own sake. States are
    `specified` so only this rule can speak; an element the loader never saw
    carries no path, and its finding's `source` is None."""

    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED),
        decisions=(
            Decision(
                id="decision:argued",
                title="Argued",
                state=State.SPECIFIED,
                reversibility=Reversibility.ONE_WAY,
                body="We cannot afford dual writes; the argument is the whole point.",
            ),
            Decision(
                id="decision:bare",
                title="Bare",
                state=State.SPECIFIED,
                reversibility=Reversibility.ONE_WAY,
                body="  \n\t\n",
            ),
            Decision(id="decision:cheap", title="Cheap", state=State.SPECIFIED, body=""),
        ),
    )

    (only,) = policy_findings(design, Index.from_design(design), today=date(2026, 8, 16))

    assert only.rule_id == "policy/one-way-needs-rationale"
    assert only.severity is Severity.ERROR
    assert only.ref == "decision:bare"
    assert only.source is None
    assert only.message == "decision:bare is a one_way decision with no rationale body"


def test_an_unknown_with_an_owner_is_not_a_finding() -> None:
    """The rule's other direction, which no fixture holds: `unknown` is a
    legitimate, expected state, and the gap the rule names is that nobody is
    accountable for resolving it — an unknown with an owner is a question on
    someone's desk, not a wish."""

    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED),
        questions=(
            Question(id="question:owned", title="Owned", state=State.UNKNOWN, owner="vinz"),
        ),
    )

    assert policy_findings(design, Index.from_design(design), today=date(2026, 8, 16)) == ()


# --- the addendum's policy rules ----------------------------------------------


def test_a_superseded_behavior_without_observations_is_still_broken() -> None:
    """The rule's reach beyond the fixture: `lifecycle` carves nothing out —
    a superseded behavior with no observations was always broken, which is why
    the severity is an error — while the adjacent active behavior, carrying
    one, says nothing. States are `specified` so only this rule can speak."""

    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED),
        components=(Component(id="component:api", title="API", state=State.SPECIFIED),),
        behaviors=(
            Behavior(
                id="behavior:retired-bare",
                title="Retired and bare",
                state=State.SPECIFIED,
                trigger="An old flow ran.",
                lifecycle=Lifecycle.SUPERSEDED,
            ),
            Behavior(
                id="behavior:watched",
                title="Watched",
                state=State.SPECIFIED,
                trigger="A flow runs.",
                observations=(
                    Observation(
                        id="behavior:watched#obs-1",
                        statement="Something is observable",
                        at="component:api",
                    ),
                ),
            ),
        ),
    )

    (only,) = policy_findings(design, Index.from_design(design), today=date(2026, 8, 16))

    assert only.rule_id == "policy/behavior-needs-observations"
    assert only.severity is Severity.ERROR
    assert only.ref == "behavior:retired-bare"
    assert only.message == "behavior:retired-bare has no observations"


def test_a_requirement_realized_only_by_superseded_behaviors_is_still_unrealized() -> None:
    """The `active` in the rule is load-bearing: supersession is recorded on
    the replacement and a superseded behavior stopped being true, so realizing
    a requirement with one is realizing it with something the system no longer
    does. The adjacent requirement, realized by an active behavior, says
    nothing — warning included, which is the severity contract's other half."""

    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED),
        components=(Component(id="component:api", title="API", state=State.SPECIFIED),),
        requirements=(
            Requirement(
                id="requirement:done",
                title="Done",
                state=State.SPECIFIED,
                realized_by=("component:api",),
            ),
            Requirement(
                id="requirement:legacy-only",
                title="Legacy only",
                state=State.SPECIFIED,
                realized_by=("component:api",),
            ),
        ),
        behaviors=(
            Behavior(
                id="behavior:current",
                title="Current",
                state=State.SPECIFIED,
                trigger="A flow runs.",
                realizes=("requirement:done",),
                observations=(
                    Observation(
                        id="behavior:current#obs-1",
                        statement="Something is observable",
                        at="component:api",
                    ),
                ),
            ),
            Behavior(
                id="behavior:retired",
                title="Retired",
                state=State.SPECIFIED,
                trigger="An old flow ran.",
                lifecycle=Lifecycle.SUPERSEDED,
                realizes=("requirement:legacy-only",),
                observations=(
                    Observation(
                        id="behavior:retired#obs-1",
                        statement="Something was observable",
                        at="component:api",
                    ),
                ),
            ),
        ),
    )

    (only,) = policy_findings(design, Index.from_design(design), today=date(2026, 8, 16))

    assert only.rule_id == "policy/requirement-needs-behavior"
    assert only.severity is Severity.WARN
    assert only.ref == "requirement:legacy-only"
    assert only.message == "requirement:legacy-only is realized by no active behavior"


def test_an_active_behavior_in_a_must_satisfy_set_is_fine() -> None:
    """The other side of `policy/superseded-in-must-satisfy`: naming an active
    behavior in `includes` is exactly what the addendum's selection is for —
    the work a slice must newly satisfy — and no finding fires."""

    design = Design(
        system=System(id="system:tiny", title="Tiny", state=State.SPECIFIED),
        components=(Component(id="component:api", title="API", state=State.SPECIFIED),),
        behaviors=(
            Behavior(
                id="behavior:current",
                title="Current",
                state=State.SPECIFIED,
                trigger="A flow runs.",
                observations=(
                    Observation(
                        id="behavior:current#obs-1",
                        statement="Something is observable",
                        at="component:api",
                    ),
                ),
            ),
        ),
        milestones=(
            Milestone(
                id="milestone:m1",
                title="M1",
                state=State.SPECIFIED,
                includes=("behavior:current",),
            ),
        ),
    )

    assert policy_findings(design, Index.from_design(design), today=date(2026, 8, 16)) == ()


@pytest.mark.parametrize(
    "rule_id",
    [
        "policy/unknown-needs-owner",
        "policy/requirement-needs-realizer",
        "policy/one-way-needs-rationale",
        "policy/external-assumptions-expired",
    ],
)
def test_every_policy_rule_is_registered_with_its_reasoning(rule_id: str) -> None:
    """`--explain ID` answers per rule id, and this is the one layer whose
    severity is a judgement call — so every policy id must sit in the catalog
    with the reasoning, the same pin the integrity layer keeps for its
    handled-upstream id."""

    assert rule_id in RULES


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
