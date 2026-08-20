"""``absicht.check``: the files, the graph, and the judgement passed on it.

Four layers, and the split between them is what these tests hold.

``store_findings`` is the layer with the least logic of its own — pydantic and
the codec already refused the file inside ``load`` — so what is pinned is the
translation: one ``LoadErrorReason`` maps to exactly one rule id at error
severity, and the message survives the codec → finding chain still naming the
offending field, because ``Finding.message`` is all an agent fixing the store
gets to read.

*Integrity* asks whether the graph holds together, which is a fact about the
design, so every one of its rules is an error: every ref resolves and stays
inside the export surface it was offered through, the C4 nesting chain is
legal, an observation points at something that can be watched, an edge joins
the kinds it is defined between, a repository prefix was declared, and nothing
loops that must not. Three ids are registered and never emitted — a model
validator refuses those shapes at parse time — and they stay in the catalogue
so ``ab check --explain`` answers for every rule we agreed.

*Policy* passes judgement on the same graph, and its severities are a posture
rather than a fact. An ``unknown`` with nobody to ask is an error because
nobody can resolve it; an unimplemented requirement is an error only once a
human reviewed it and a warning while it is still assumed; stale-but-routine —
a lapsed assumption, an expired external service — stays a warning, because a
checker that fails on an honest brownfield reading teaches people to stop
recording it.

*Landscape* owns what one design cannot answer about itself: whether its
imports exist, whether the versions agree, whether an id is unique across
everything indexed together, whether the import graph is acyclic.

Two decisions run through all four. The clock is a parameter and never
``date.today()``, so an expiry case says "past as of when" and no test depends
on the calendar. And each case is read through the one rule it was built to
trip, because ``check`` runs every rule over every design: a rule's "trips"
case sits beside its "does not trip" neighbour rather than in a design pruned
until only one rule can speak.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from absicht.check import check, check_landscape, expired_services, store_findings
from absicht.findings import RULES, Finding, Severity
from absicht.load import LoadedStore, LoadError, LoadErrorReason, load_store
from absicht.models.design import (
    Assumption,
    Behavior,
    Component,
    ComponentLevel,
    Confidence,
    Decision,
    Design,
    ExternalService,
    Goal,
    Import,
    Interface,
    InterfaceStyle,
    Note,
    Observation,
    Outcome,
    QualityAttribute,
    QualityRequirement,
    Question,
    Relationship,
    RelationshipType,
    Requirement,
    Resource,
    ResourceKind,
    Reversibility,
    State,
)
from absicht.resolve import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "systems"

TODAY = date(2026, 6, 1)
"""The run's clock, stated once. No rule reads `date.today()`, so every expiry
case below is "past as of this date" and the suite never turns on the
calendar."""


# --------------------------------------------------------------------- helpers


def _design(name: str) -> Design:
    return resolve(load_store(FIXTURES / name))


def _tiny(**fields: object) -> Design:
    """A design with a header and whatever one case needs, and nothing else."""
    return Design(id="design:tiny", title="Tiny", version="0.1.0", **fields)


def _ids(findings: Iterable[Finding]) -> list[str]:
    return [found.rule_id for found in findings]


def _under(findings: Iterable[Finding], rule_id: str) -> list[Finding]:
    """The findings one rule produced. Every case reads its answer through
    this, because `check` runs every rule over every design and a case built
    to trip one of them says nothing about the rest."""
    return [found for found in findings if found.rule_id == rule_id]


def _one(findings: Iterable[Finding], rule_id: str) -> Finding:
    (only,) = _under(findings, rule_id)
    return only


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _component(ref: str, title: str, **fields: object) -> Component:
    fields.setdefault("level", ComponentLevel.SYSTEM)
    return Component(id=ref, title=title, **fields)


def _behavior(ref: str, at: str, **fields: object) -> Behavior:
    return Behavior(
        id=ref,
        title=ref,
        trigger="Something happens.",
        observations=(Observation(id=f"{ref}#obs-1", statement="It lands.", at=at),),
        **fields,
    )


# ----------------------------------------------------------------- store layer


RULE_BY_REASON = {
    LoadErrorReason.SYNTAX: "store/yaml-syntax",
    LoadErrorReason.VALIDATION: "store/validation",
    LoadErrorReason.MISSING_DESIGN: "store/design-missing",
    LoadErrorReason.IO: "store/unreadable-file",
}
"""The translation table, restated per reason: a reason added to the enum
without a rule (there or here) fails loudly rather than reporting "something
is wrong" under a borrowed id."""


@pytest.mark.parametrize("reason", list(LoadErrorReason))
def test_every_load_error_reason_becomes_its_rule_at_error_severity(
    reason: LoadErrorReason,
) -> None:
    loaded = LoadedStore(
        errors=(LoadError(path="components/x.md", message="what went wrong", reason=reason),)
    )

    (only,) = store_findings(loaded)

    assert only.rule_id == RULE_BY_REASON[reason]
    assert only.severity is Severity.ERROR
    assert only.source == "components/x.md"
    assert only.message == "what went wrong"


def test_the_broken_store_reports_exactly_its_three_parse_failures() -> None:
    """`broken/` holds one clearly-named file per failure family; only three
    fail before the graph exists. The rest parse on purpose — a dangling ref,
    a nesting cycle and the policy cases are the layers above's to judge, not
    files the loader refused."""

    by_path = {found.source: found for found in store_findings(load_store(FIXTURES / "broken"))}

    assert set(by_path) == {
        "requirements/garbage.md",
        "behaviors/bad-anchor.md",
        "behaviors/bad-timing.md",
    }

    garbage = by_path["requirements/garbage.md"]
    assert garbage.rule_id == "store/yaml-syntax"
    assert "invalid YAML" in garbage.message

    # A whole-record validator reports at `(root)`, so the message itself has
    # to name what it rejected: the observation, and the behavior it should
    # have been anchored to.
    bad_anchor = by_path["behaviors/bad-anchor.md"]
    assert bad_anchor.rule_id == "store/validation"
    assert (
        "observation 'behavior:somewhere-else#obs-1' is not anchored to 'behavior:bad-anchor'"
        in bad_anchor.message
    )

    bad_timing = by_path["behaviors/bad-timing.md"]
    assert bad_timing.rule_id == "store/validation"
    assert "`must_not` means at no point: omit `timing`" in bad_timing.message


@pytest.mark.parametrize("name", ["clean", "brownfield", "composite"])
def test_stores_that_parse_have_no_store_findings(name: str) -> None:
    """`brownfield/` gives the policy layer plenty to say later; none of it is
    a parse failure, and this layer must not reach for it. An `observed`
    element with no rationale is the honest brownfield default, not a broken
    file."""

    assert store_findings(load_store(FIXTURES / name)) == []


def test_a_field_violation_names_the_field_in_the_message(tmp_path: Path) -> None:
    """A pydantic `ValidationError` must survive the `CodecError` → `Finding`
    chain naming the offending field, not just "validation failed"."""

    _write(tmp_path, "design.yaml", "id: design:tiny\ntitle: Tiny\nversion: 0.1.0\n")
    _write(tmp_path, "components/bad-id.md", "---\nid: Not a Ref\ntitle: X\nlevel: system\n---\n")

    (only,) = store_findings(load_store(tmp_path))

    assert only.rule_id == "store/validation"
    assert "id: String should match pattern" in only.message


def test_a_store_with_no_design_yaml_is_reported_as_the_store_being_wrong(tmp_path: Path) -> None:
    """Not a file that failed to parse: a store is one design, and one without
    an id, a title and a version cannot be folded or pointed at. The finding
    carries no source, because no file is the culprit."""

    _write(
        tmp_path, "components/kept.md", "---\nid: component:kept\ntitle: K\nlevel: system\n---\n"
    )

    (only,) = store_findings(load_store(tmp_path))

    assert only.rule_id == "store/design-missing"
    assert only.severity is Severity.ERROR
    assert only.source == "design.yaml"


# ------------------------------------------------------------ the whole report


def test_broken_reports_one_finding_family_per_file_worst_first() -> None:
    """The graph layers' whole report over `broken/`, in the order `check`
    returns it: errors before warnings, then by rule id, then by element — so
    `ab check --rule X` points at exactly the file named after X, and the two
    ids that fire twice do so because two files break them.

    The store layer is absent by construction: it reads load errors and this
    reads the design that the surviving files folded into.
    """

    assert _ids(check(_design("broken"), today=TODAY)) == [
        "integrity/component-level",
        "integrity/component-level",
        "integrity/cycle",
        "integrity/cycle",
        "integrity/dangling-ref",
        "integrity/dangling-ref",
        "integrity/edge-kinds",
        "integrity/interface-on-resource",
        "integrity/observation-target",
        "integrity/repository-unknown",
        "policy/behavior-unobserved",
        "policy/milestone-unscoped",
        "policy/unknown-unowned",
        "policy/agency-undeclared",
        "policy/external-assumption-expired",
        "policy/goal-unmeasured",
        "policy/requirement-unrealized",
    ]


def test_worst_first_groups_the_severities_and_orders_within_a_rule_by_element() -> None:
    """Why the order is worth pinning at all: the first line of a report is
    what a human reads, so nothing advisory may precede something broken, and
    a rule that fired twice names its elements in a stable order rather than
    in whichever order the walk happened to reach them."""

    findings = check(_design("broken"), today=TODAY)

    ranks = [found.severity.rank for found in findings]
    assert ranks == sorted(ranks, reverse=True)
    assert [found.ref for found in _under(findings, "integrity/component-level")] == [
        "component:loop-a",
        "component:loop-b",
    ]


def test_the_clean_store_reports_only_the_advisory_count() -> None:
    """A complete, internally consistent design still says one thing: how many
    `should` observations exist. They never fail verification, which is what
    makes them a dumping ground, so the count stays visible."""

    (only,) = check(_design("clean"), today=TODAY)

    assert only.rule_id == "policy/advisory-count"
    assert only.severity is Severity.INFO
    assert only.message == "1 advisory observations never fail verification"


def test_the_composite_store_is_silent() -> None:
    """One design over two repositories, with no advisory observation to
    count: the multi-repository shape adds no findings of its own."""

    assert check(_design("composite"), today=TODAY) == []


def test_brownfield_grades_its_one_gap_an_error_and_the_rest_warnings() -> None:
    """An honest reading of a legacy system, and the severities that make it
    usable: the unowned `unknown` is the one thing nobody can resolve, and
    every other gap — unimplemented, unrealized, aimless, an external whose
    assumptions lapsed — is a state a brownfield design legitimately holds."""

    findings = check(_design("brownfield"), today=TODAY)

    assert [(found.rule_id, found.severity) for found in findings] == [
        ("policy/unknown-unowned", Severity.ERROR),
        ("policy/external-assumption-expired", Severity.WARN),
        ("policy/requirement-aimless", Severity.WARN),
        ("policy/requirement-unimplemented", Severity.WARN),
        ("policy/requirement-unrealized", Severity.WARN),
    ]


# ------------------------------------------------------------------- integrity


def test_a_dangling_ref_names_the_carrier_the_field_and_the_missing_target() -> None:
    """Both shapes a ref comes in, from the two files `broken/` names after
    them. An observation is a nested record, so the finding is attributed to
    the behavior that carries it while the message names the observation —
    that is what lets one generic walk cover a field the rule never heard of.
    An authored edge belongs to no file, so it carries no source."""

    observation, edge = _under(check(_design("broken"), today=TODAY), "integrity/dangling-ref")

    assert observation.severity is Severity.ERROR
    assert observation.ref == "behavior:dangling-observation"
    assert observation.source == "behaviors/dangling-observation.md"
    assert observation.message == (
        "behavior:dangling-observation#obs-1.at points at resource:ghost-store"
    )

    assert edge.severity is Severity.ERROR
    assert edge.ref == "component:dangling"
    assert edge.source is None
    assert edge.message == "implements edge target_id points at req:ghost"


def test_reaching_past_an_imports_export_surface_is_not_a_dangling_ref() -> None:
    """The target is there; the boundary is what was crossed, and the two want
    different edits. Reaching a private id makes the other design's internals
    your dependency, so it is named as such — while the same ref with the
    other design absent reads as dangling, which is the honest answer when it
    was never fetched."""

    other = Design(
        id="design:payments",
        title="Payments",
        version="1.0.0",
        exports=("interface:charges",),
        interfaces=(Interface(id="interface:charges", title="Charges", style=InterfaceStyle.HTTP),),
        components=(_component("component:ledger", "Ledger"),),
    )
    mine = _tiny(
        imports=(Import(id="design:payments", source="../payments", expects=">=1.0.0"),),
        components=(_component("component:mine", "Mine"),),
        relationships=(
            Relationship(
                source_id="component:mine",
                target_id="component:ledger",
                type=RelationshipType.DEPENDS_ON,
            ),
        ),
    )

    resolved = check(mine, imports={"design:payments": other}, today=TODAY)
    unresolved = check(mine, today=TODAY)

    assert _one(resolved, "integrity/not-exported").message == (
        "depends_on edge target_id points at component:ledger"
    )
    assert _under(resolved, "integrity/dangling-ref") == []
    assert _under(unresolved, "integrity/not-exported") == []
    assert _ids(_under(unresolved, "integrity/dangling-ref")) == ["integrity/dangling-ref"]


def test_an_exported_ref_may_only_name_something_this_design_declares() -> None:
    """You may export only what you declare: to offer somebody else's
    interface, wrap it in one of yours, which makes it yours to keep. The
    kind rule beside it — a goal or a component never crosses a boundary — is
    `Design`'s own validator, registered here and enforced upstream."""

    findings = check(_tiny(exports=("interface:nowhere",)), today=TODAY)

    only = _one(findings, "integrity/export-undefined")
    assert only.severity is Severity.ERROR
    assert only.ref == "design:tiny"
    assert only.message == "design:tiny exports interface:nowhere, which it does not define"


def test_the_rules_a_model_validator_already_enforces_stay_in_the_catalogue() -> None:
    """Three shapes a record simply cannot have, so no rule here can ever emit
    them: a non-contract export, a `must_not` that says when, an observation
    anchored to another behavior. They surface as `store/validation` on the
    file, and their ids stay registered so `--explain` answers for every rule
    we agreed rather than silently dropping three."""

    for rule_id in (
        "integrity/export-kind",
        "integrity/must-not-has-timing",
        "integrity/observations-anchored",
    ):
        assert RULES[rule_id].startswith("Handled upstream")


LEVEL_CASES = [
    (ComponentLevel.SYSTEM, None, None),
    (ComponentLevel.SYSTEM, "component:root", "component:child is a system and has a parent"),
    (ComponentLevel.CONTAINER, "component:root", None),
    (
        ComponentLevel.CONTAINER,
        None,
        "component:child is a container with no parent system",
    ),
    (
        ComponentLevel.CONTAINER,
        "component:leaf",
        "component:child is a container; its parent must be a system",
    ),
    (ComponentLevel.COMPONENT, "component:box", None),
    (
        ComponentLevel.COMPONENT,
        "component:root",
        "component:child is a component; its parent must be a container",
    ),
    (
        ComponentLevel.COMPONENT,
        "resource:store",
        "component:child is a component; its parent must be a container",
    ),
]


@pytest.mark.parametrize(("level", "parent", "expected"), LEVEL_CASES)
def test_the_c4_nesting_chain_is_the_zoom_and_a_broken_link_is_an_error(
    level: ComponentLevel, parent: str | None, expected: str | None
) -> None:
    """Nesting is the zoom, so a broken chain makes every diagram wrong: a
    system has no parent, a container's parent is a system, a component's
    parent is a container. A parent that resolves to something that is not a
    component at all is the same failure — the ref is fine, the shape is not.
    """

    design = _tiny(
        components=(
            _component("component:root", "Root"),
            _component(
                "component:box", "Box", level=ComponentLevel.CONTAINER, parent="component:root"
            ),
            _component(
                "component:leaf", "Leaf", level=ComponentLevel.COMPONENT, parent="component:box"
            ),
            _component("component:child", "Child", level=level, parent=parent),
        ),
        resources=(
            Resource(
                id="resource:store",
                title="Store",
                resource_kind=ResourceKind.STORE,
                technology="Redis",
            ),
        ),
    )

    about_child = [
        found
        for found in check(design, today=TODAY)
        if found.rule_id == "integrity/component-level" and found.ref == "component:child"
    ]

    assert [found.message for found in about_child] == ([expected] if expected else [])


def test_each_acyclic_relation_is_its_own_graph_and_names_its_whole_loop() -> None:
    """`broken/`'s two loops, pinned exactly: the message is user-facing and
    must stay deterministic, closed path included. Nesting and supersession
    are separate directed graphs, so one loop never masks the other, and each
    is reported once rather than once per edge."""

    messages = [
        found.message for found in _under(check(_design("broken"), today=TODAY), "integrity/cycle")
    ]

    assert messages == [
        "supersedes cycle: behavior:supersede-a -> behavior:supersede-b -> behavior:supersede-a",
        "component nesting cycle: component:loop-a -> component:loop-b -> component:loop-a",
    ]


def test_disjoint_cycles_are_one_finding_each_not_one_per_edge() -> None:
    """A two-node loop and a three-node loop in the same relation: two
    findings, one per distinct cycle. Five edges produce two lines, not five —
    the reader is told what is wrong, not everything that is part of it."""

    design = _tiny(
        components=(
            _component(
                "component:two-a", "Two A", level=ComponentLevel.CONTAINER, parent="component:two-b"
            ),
            _component(
                "component:two-b", "Two B", level=ComponentLevel.CONTAINER, parent="component:two-a"
            ),
            _component(
                "component:three-a",
                "Three A",
                level=ComponentLevel.CONTAINER,
                parent="component:three-b",
            ),
            _component(
                "component:three-b",
                "Three B",
                level=ComponentLevel.CONTAINER,
                parent="component:three-c",
            ),
            _component(
                "component:three-c",
                "Three C",
                level=ComponentLevel.CONTAINER,
                parent="component:three-a",
            ),
        ),
    )

    cycles = _under(check(design, today=TODAY), "integrity/cycle")

    assert len(cycles) == 2
    members = sorted(
        sorted(component.id for component in design.components if component.id in found.message)
        for found in cycles
    )
    assert members == [
        ["component:three-a", "component:three-b", "component:three-c"],
        ["component:two-a", "component:two-b"],
    ]


def test_a_dependency_loop_is_the_same_rule_on_a_different_relation() -> None:
    """`depends_on` is checked as its own directed graph: two containers that
    each need the other loop with no nesting broken and no supersession
    involved, and "before" going undefined is the same failure."""

    design = _tiny(
        components=(
            _component("component:root", "Root"),
            _component("component:a", "A", level=ComponentLevel.CONTAINER, parent="component:root"),
            _component("component:b", "B", level=ComponentLevel.CONTAINER, parent="component:root"),
        ),
        relationships=(
            Relationship(
                source_id="component:a", target_id="component:b", type=RelationshipType.DEPENDS_ON
            ),
            Relationship(
                source_id="component:b", target_id="component:a", type=RelationshipType.DEPENDS_ON
            ),
        ),
    )

    only = _one(check(design, today=TODAY), "integrity/cycle")

    assert only.severity is Severity.ERROR
    assert only.message == "depends_on cycle: component:a -> component:b -> component:a"


EDGE_CASES = [
    (RelationshipType.CALLS, "component:one", "interface:port", None),
    (
        RelationshipType.CALLS,
        "component:one",
        "resource:store",
        "calls ends at resource:store; it ends at ['design', 'external', 'interface']",
    ),
    (
        RelationshipType.IMPLEMENTS,
        "behavior:watcher",
        "req:one",
        "implements starts at behavior:watcher; it starts at ['component']",
    ),
    (
        RelationshipType.REALIZES,
        "component:one",
        "req:one",
        "realizes starts at component:one; it starts at ['behavior']",
    ),
    (RelationshipType.RELATES_TO, "resource:store", "req:one", None),
]


@pytest.mark.parametrize(("edge_type", "source", "target", "expected"), EDGE_CASES)
def test_a_relationship_must_join_the_kinds_it_is_defined_between(
    edge_type: RelationshipType, source: str, target: str, expected: str | None
) -> None:
    """The edge kind is what a checker branches on, so a wrong one silently
    disables every rule behind it. Both ends are policed, and `relates_to` —
    the weakest edge, which carries no rule — is deliberately free at both."""

    design = _tiny(
        components=(_component("component:one", "One"),),
        interfaces=(Interface(id="interface:port", title="Port", style=InterfaceStyle.CALL),),
        resources=(
            Resource(
                id="resource:store",
                title="Store",
                resource_kind=ResourceKind.STORE,
                technology="Redis",
            ),
        ),
        requirements=(Requirement(id="req:one", title="One", statement="It must work."),),
        behaviors=(_behavior("behavior:watcher", "component:one"),),
        relationships=(Relationship(source_id=source, target_id=target, type=edge_type),),
    )

    messages = [
        found.message for found in _under(check(design, today=TODAY), "integrity/edge-kinds")
    ]

    assert messages == ([expected] if expected else [])


OBSERVABLE_TARGETS = ["component:one", "interface:port", "resource:store", "behavior:other"]


@pytest.mark.parametrize("at", OBSERVABLE_TARGETS)
def test_the_four_kinds_an_observation_may_watch_trip_nothing(at: str) -> None:
    """A component, an interface, a resource or another behavior can be
    watched — the fourth is composition, which is why it belongs in the same
    list rather than in a rule of its own."""

    design = _tiny(
        components=(_component("component:one", "One"),),
        interfaces=(Interface(id="interface:port", title="Port", style=InterfaceStyle.CALL),),
        resources=(
            Resource(
                id="resource:store",
                title="Store",
                resource_kind=ResourceKind.STORE,
                technology="Redis",
            ),
        ),
        behaviors=(
            _behavior("behavior:one", at),
            _behavior("behavior:other", "component:one"),
        ),
    )

    assert _under(check(design, today=TODAY), "integrity/observation-target") == []


def test_an_observation_on_something_nobody_can_watch_is_an_error() -> None:
    """`broken/`'s decision: the ref resolves, so this is not a dangling one —
    a requirement, a goal or a decision is a statement about the system and
    not a place where something happens."""

    only = _one(check(_design("broken"), today=TODAY), "integrity/observation-target")

    assert only.severity is Severity.ERROR
    assert only.ref == "behavior:observation-at-decision"
    assert only.source == "behaviors/observation-at-decision.md"
    assert only.message == (
        "behavior:observation-at-decision#obs-1 watches decision:one-way-no-why, "
        "which cannot be watched"
    )


def test_an_external_service_may_only_name_a_design_some_import_declares() -> None:
    """The box has to point at something we actually pulled in, or the
    contract behind it cannot be read at all."""

    design = _tiny(
        external_services=(
            ExternalService(id="external:payments", title="Payments", design="design:payments"),
        ),
    )

    only = _one(check(design, today=TODAY), "integrity/external-design-unknown")

    assert only.severity is Severity.ERROR
    assert only.ref == "external:payments"
    assert only.message == ("external:payments names design:payments, which no import declares")


def test_an_interface_belongs_to_the_external_service_only_where_it_has_no_design() -> None:
    """The two cases the model draws. Where the other side publishes a design,
    its exports are the contract and a copy here would be a second opinion
    about it. Where it has none — Stripe — the interface we require is ours to
    write and ours to keep current, and saying so trips nothing."""

    backed = _tiny(
        imports=(Import(id="design:payments", source="../payments", expects=">=1.0.0"),),
        external_services=(
            ExternalService(id="external:payments", title="Payments", design="design:payments"),
        ),
        interfaces=(
            Interface(
                id="interface:charges",
                title="Charges",
                style=InterfaceStyle.HTTP,
                declared_by="external:payments",
            ),
        ),
    )
    undocumented = backed.model_copy(
        update={
            "imports": (),
            "external_services": (ExternalService(id="external:payments", title="Payments"),),
        }
    )

    only = _one(check(backed, today=TODAY), "integrity/external-design-interface")
    assert only.severity is Severity.ERROR
    assert only.ref == "interface:charges"
    assert only.message == (
        "interface:charges is declared by external:payments, which has its own design"
    )

    assert _under(check(undocumented, today=TODAY), "integrity/external-design-interface") == []


def test_an_interface_declared_by_a_resource_is_an_error_naming_the_owner() -> None:
    """`broken/`'s legacy cache: the ref resolves, and the kind it points at
    is the defect. A resource takes part in no contract — a component's
    relation to one is a dependency, and the observations pointing at it are
    what give it meaning — so the fix has a place to land."""

    only = _one(check(_design("broken"), today=TODAY), "integrity/interface-on-resource")

    assert only.severity is Severity.ERROR
    assert only.ref == "interface:legacy-cache"
    assert only.source == "interfaces/legacy-cache.md"
    assert only.message == (
        "interface:legacy-cache is declared by the resource resource:audit-store"
    )


def test_an_implemented_by_prefix_no_repository_declares_is_an_error() -> None:
    """The link into code has to resolve to a URL and a ref rather than to a
    guess. `composite/` is the adjacent case: one design over two declared
    repositories, with the same field pointing into both and nothing to say."""

    only = _one(check(_design("broken"), today=TODAY), "integrity/repository-unknown")

    assert only.severity is Severity.ERROR
    assert only.ref == "component:wrong-repo"
    assert only.source == "components/wrong-repo.md"
    assert only.message == "component:wrong-repo points into the undeclared repository 'ghost'"

    assert _under(check(_design("composite"), today=TODAY), "integrity/repository-unknown") == []


# ---------------------------------------------------------------------- policy


@pytest.mark.parametrize(
    ("confidence", "severity"),
    [
        (Confidence.ASSUMED, Severity.WARN),
        (Confidence.REVIEWED, Severity.ERROR),
        (Confidence.VERIFIED, Severity.ERROR),
    ],
)
def test_an_unimplemented_requirement_hardens_once_a_human_reviewed_it(
    confidence: Confidence, severity: Severity
) -> None:
    """The severity split that makes the rule usable mid-design: somebody
    agreed to build it and nothing claims to is an error, while the same gap
    under an assumed requirement is a warning — nobody has read it yet."""

    design = _tiny(
        requirements=(
            Requirement(
                id="req:one", title="One", statement="It must work.", confidence=confidence
            ),
        ),
    )

    assert _one(check(design, today=TODAY), "policy/requirement-unimplemented").severity is severity


def test_a_requirement_a_component_implements_and_a_behavior_realizes_is_quiet() -> None:
    """The two edges the coverage rules read, and what each one answers: a
    component says it was built, a behavior says how you would know. Both
    present, and neither rule speaks."""

    design = _tiny(
        goals=(
            Goal(
                id="goal:one",
                title="One",
                outcome="Things work",
                measure="uptime",
                state=State.SPECIFIED,
            ),
        ),
        requirements=(
            Requirement(
                id="req:one",
                title="One",
                statement="It must work.",
                state=State.SPECIFIED,
                confidence=Confidence.REVIEWED,
            ),
        ),
        components=(_component("component:one", "One", state=State.SPECIFIED),),
        behaviors=(_behavior("behavior:one", "component:one", state=State.SPECIFIED),),
        relationships=(
            Relationship(
                source_id="component:one", target_id="req:one", type=RelationshipType.IMPLEMENTS
            ),
            Relationship(
                source_id="behavior:one", target_id="req:one", type=RelationshipType.REALIZES
            ),
            Relationship(
                source_id="req:one", target_id="goal:one", type=RelationshipType.DERIVES_FROM
            ),
        ),
    )

    assert check(design, today=TODAY) == []


def test_a_requirement_nothing_realizes_is_a_warning_naming_what_is_missing() -> None:
    """`broken/`'s one file for it: a component implements it, so the
    unimplemented rule stays quiet and the file trips exactly one thing. The
    requirement may be true and merely unobserved, which is a normal state
    mid-design, so it is a warning."""

    only = _one(check(_design("broken"), today=TODAY), "policy/requirement-unrealized")

    assert only.severity is Severity.WARN
    assert only.ref == "req:no-behavior"
    assert only.source == "requirements/no-behavior.md"
    assert only.message == "no behavior says how you would know req:no-behavior holds"


def test_a_requirement_derived_only_from_another_requirement_still_has_no_aim() -> None:
    """`derives_from` reaches a parent requirement or a goal, and only the
    goal answers why the thing exists. A chain that never reaches one is
    aimless however long it is — a warning, because the goal may simply not be
    written yet."""

    parented = _tiny(
        requirements=(
            Requirement(id="req:parent", title="Parent", statement="It must work."),
            Requirement(id="req:child", title="Child", statement="It must work here."),
        ),
        relationships=(
            Relationship(
                source_id="req:child", target_id="req:parent", type=RelationshipType.DERIVES_FROM
            ),
        ),
    )

    aimless = _under(check(parented, today=TODAY), "policy/requirement-aimless")

    assert [found.ref for found in aimless] == ["req:child", "req:parent"]
    assert {found.severity for found in aimless} == {Severity.WARN}


def test_a_goal_nothing_serves_is_an_error_and_one_without_a_measure_a_warning() -> None:
    """The two halves of a goal, graded apart. Nothing deriving from it means
    it is finished, abandoned or a slogan, and each of those wants a different
    edit — so it is an error. Stating no measure is a warning: the goal is
    real, and nobody can yet tell whether it was met."""

    design = _tiny(goals=(Goal(id="goal:one", title="One", outcome="Things work"),))

    findings = check(design, today=TODAY)

    assert _one(findings, "policy/goal-unserved").severity is Severity.ERROR
    assert _one(findings, "policy/goal-unmeasured").severity is Severity.WARN
    assert _one(findings, "policy/goal-unmeasured").message == "goal:one states no measure"


def test_a_behavior_with_no_observations_is_an_error() -> None:
    """It says something happens and never says what, so verification has
    nothing to check. `clean/`'s three behaviors all observe something and say
    nothing here."""

    only = _one(check(_design("broken"), today=TODAY), "policy/behavior-unobserved")

    assert only.severity is Severity.ERROR
    assert only.ref == "behavior:no-observations"
    assert only.source == "behaviors/no-observations.md"


@pytest.mark.parametrize(
    ("state", "reversibility", "expected"),
    [
        (State.CONSTRAINED, None, True),
        (State.DELEGATED, None, True),
        (State.CONSTRAINED, Reversibility.ONE_WAY, False),
        (State.DELEGATED, Reversibility.CHEAP, False),
        (State.SPECIFIED, None, False),
        (State.OBSERVED, None, False),
    ],
)
def test_an_element_that_lets_an_agent_decide_must_say_what_being_wrong_costs(
    state: State, reversibility: Reversibility | None, expected: bool
) -> None:
    """`constrained` and `delegated` hand an agent a decision; without a
    `reversibility` it cannot judge whether to decide freely, propose first,
    or stop and ask. Every other state decides nothing, so it needs no cost."""

    design = _tiny(
        decisions=(
            Decision(
                id="decision:one",
                title="One",
                choice="Do it this way",
                state=state,
                reversibility=reversibility,
                owner="dana",
            ),
        ),
    )

    findings = _under(check(design, today=TODAY), "policy/agency-undeclared")

    assert bool(findings) is expected
    assert all(found.severity is Severity.WARN for found in findings)


def test_an_unknown_with_nobody_to_ask_is_the_errors_of_the_policy_layer() -> None:
    """`unknown` means ask, so an error here is the honest one: with nobody to
    ask the state is a wish, and an agent will invent instead. An owner is the
    whole fix — the same element with one is silent."""

    unowned = _tiny(
        questions=(
            Question(id="question:one", title="One", question="Which way?", state=State.UNKNOWN),
        ),
    )
    owned = unowned.model_copy(
        update={"questions": (unowned.questions[0].model_copy(update={"owner": "dana"}),)}
    )

    only = _one(check(unowned, today=TODAY), "policy/unknown-unowned")
    assert only.severity is Severity.ERROR
    assert only.message == "question:one is unknown and has nobody to ask"

    assert _under(check(owned, today=TODAY), "policy/unknown-unowned") == []


@pytest.mark.parametrize(
    ("expires_on", "expired"),
    [
        (date(2026, 5, 31), True),
        (date(2026, 6, 1), False),  # the boundary: `expires_on` is the last good day
        (date(2026, 6, 2), False),
        (None, False),
    ],
)
def test_expiry_is_answered_against_the_clock_the_caller_passed(
    expires_on: date | None, expired: bool
) -> None:
    """The clock is a parameter, so a run answers "expired as of when" and
    stays reproducible. An assumption and an external service lapse by the
    same comparison and grade the same warning — stale-but-routine, though
    everything the assumption `invalidates` is now unproven."""

    design = _tiny(
        assumptions=(
            Assumption(
                id="assumption:one",
                title="One",
                statement="The provider stays put.",
                expires_on=expires_on,
            ),
        ),
        external_services=(ExternalService(id="external:one", title="One", expires_on=expires_on),),
    )

    findings = check(design, today=TODAY)

    assert bool(_under(findings, "policy/assumption-expired")) is expired
    assert bool(_under(findings, "policy/external-assumption-expired")) is expired
    assert all(found.severity is Severity.WARN for found in findings if "expired" in found.rule_id)


def test_expired_services_is_the_one_spelling_of_which_services_lapsed() -> None:
    """`ab gaps` puts the same fact on its worklist, so a warning and a
    worklist row can never disagree about which services lapsed. The boundary
    is the same one the rule uses: `expires_on` is the last good day."""

    design = _tiny(
        external_services=(
            ExternalService(id="external:lapsed", title="Lapsed", expires_on=date(2026, 5, 31)),
            ExternalService(id="external:today", title="Today", expires_on=TODAY),
            ExternalService(id="external:never", title="Never"),
        ),
    )

    assert [service.id for service in expired_services(design, today=TODAY)] == ["external:lapsed"]


def test_an_import_with_no_version_range_cannot_warn_when_the_other_side_moves() -> None:
    """The same gap as a dependency with no version range: a warning, because
    the import works today and nothing will ever say when it stopped."""

    design = _tiny(imports=(Import(id="design:payments", source="../payments"),))

    only = _one(check(design, today=TODAY), "policy/import-unpinned")

    assert only.severity is Severity.WARN
    assert only.ref == "design:payments"
    assert only.message == "design:payments is imported with no version range"


@pytest.mark.parametrize(
    ("evidence", "claimed", "expected"),
    [
        ((), True, True),
        (("bench/cancel.py",), True, False),
        ((), False, False),  # nobody claimed it, so nothing was left unmeasured
    ],
)
def test_a_quality_is_unevidenced_only_where_a_component_claims_to_satisfy_it(
    evidence: tuple[str, ...], claimed: bool, expected: bool
) -> None:
    """The claim may be true; nothing measured it. Without the `satisfies`
    edge there is no claim to check, which is why an unclaimed quality with no
    evidence says nothing — that is the requirement waiting, not a lie."""

    design = _tiny(
        components=(_component("component:one", "One"),),
        qualities=(
            QualityRequirement(
                id="quality:latency",
                title="Fast",
                attribute=QualityAttribute.LATENCY,
                evidence=evidence,
            ),
        ),
        relationships=(
            (
                Relationship(
                    source_id="component:one",
                    target_id="quality:latency",
                    type=RelationshipType.SATISFIES,
                ),
            )
            if claimed
            else ()
        ),
    )

    assert bool(_under(check(design, today=TODAY), "policy/quality-unevidenced")) is expected


def test_a_milestone_with_no_scope_says_nothing_about_what_may_be_touched() -> None:
    """An error, because the packet cannot be assembled from it: an agent
    given a slice with no boundary either asks about everything or touches
    everything. `clean/`'s milestone names two components and is silent."""

    only = _one(check(_design("broken"), today=TODAY), "policy/milestone-unscoped")

    assert only.severity is Severity.ERROR
    assert only.ref == "milestone:unscoped"
    assert only.source == "milestones/unscoped.md"

    assert _under(check(_design("clean"), today=TODAY), "policy/milestone-unscoped") == []


def test_a_note_about_something_nothing_defines_is_information_and_never_a_failure() -> None:
    """A note about something not yet written is the normal case, so this is
    the one `policy/` rule that is `info` by design. The point of the typed
    link is that a rename surfaces it rather than stranding it in prose."""

    design = _tiny(
        components=(_component("component:one", "One"),),
        notes=(
            Note(
                id="note:a1b2c3",
                created_on=date(2026, 5, 1),
                text="Think about this.",
                about=("component:one", "component:not-yet"),
            ),
        ),
    )

    only = _one(check(design, today=TODAY), "policy/note-dangling")

    assert only.severity is Severity.INFO
    assert only.ref == "note:a1b2c3"
    assert only.message == "note:a1b2c3 is about component:not-yet, which nothing defines"


def test_advisory_observations_are_counted_only_when_there_are_any() -> None:
    """They never fail verification, which is what makes them a dumping
    ground, so the count is reported to keep it visible. A design with none
    gets no line — a zero would be noise on every clean run."""

    advisory = Observation(
        id="behavior:one#obs-2",
        statement="It is quick.",
        at="component:one",
        outcome=Outcome.SHOULD,
    )
    required = _tiny(
        components=(_component("component:one", "One"),),
        behaviors=(_behavior("behavior:one", "component:one"),),
    )
    with_advisory = required.model_copy(
        update={
            "behaviors": (
                required.behaviors[0].model_copy(
                    update={"observations": (*required.behaviors[0].observations, advisory)}
                ),
            )
        }
    )

    assert _under(check(required, today=TODAY), "policy/advisory-count") == []
    assert _one(check(with_advisory, today=TODAY), "policy/advisory-count").message == (
        "1 advisory observations never fail verification"
    )


# ------------------------------------------------------------------- landscape


def _payments(**fields: object) -> Design:
    """The design the landscape cases import: one export, and nothing else to
    say about it."""
    return Design(
        id="design:payments",
        title="Payments",
        version="1.2.0",
        exports=("interface:charges",),
        interfaces=(Interface(id="interface:charges", title="Charges", style=InterfaceStyle.HTTP),),
        **fields,
    )


def _orders(*, expects: str = ">=1.0.0", consumes: bool = True, **fields: object) -> Design:
    """The importer: it declares what it expects of `design:payments`, and by
    default it actually calls the interface that design offered."""
    extra = cast("tuple[Component, ...]", fields.pop("components", ()))
    return Design(
        id="design:orders",
        title="Orders",
        version="1.0.0",
        imports=(Import(id="design:payments", source="../payments", expects=expects),),
        components=(_component("component:orders", "Orders"), *extra),
        relationships=(
            (
                Relationship(
                    source_id="component:orders",
                    target_id="interface:charges",
                    type=RelationshipType.CALLS,
                ),
            )
            if consumes
            else ()
        ),
        **fields,
    )


def test_two_designs_claiming_one_id_make_every_foreign_lookup_ambiguous() -> None:
    """Every ref resolves against one index built from the whole landscape, so
    a repeated design id has no answer. The second is dropped rather than
    merged: guessing which one a ref meant is the failure this reports."""

    findings = check_landscape([_payments(), _payments()], today=TODAY)

    only = _one(findings, "landscape/duplicate-design")
    assert only.severity is Severity.ERROR
    assert only.message == "two designs claim design:payments"


def test_an_import_the_landscape_does_not_hold_names_where_it_was_looked_for() -> None:
    """Nothing after it can be trusted for that design: every ref into the
    missing design reads as dangling, which is the honest cascade rather than
    a silent pass."""

    findings = check_landscape([_orders()], today=TODAY)

    only = _one(findings, "landscape/import-unresolved")
    assert only.severity is Severity.ERROR
    assert only.ref == "design:orders"
    assert only.message == (
        "design:orders imports design:payments from '../payments', which is not here"
    )
    assert _under(findings, "design:orders: implements edge target_id points at req:ghost") == []


def test_two_designs_that_import_each_other_are_one_design() -> None:
    """Neither can be released without the other, so the cycle is an error
    rather than a note. It is the import graph's own walk, so the message
    names the whole loop the way every other cycle does."""

    findings = check_landscape(
        [
            _payments(imports=(Import(id="design:orders", source="../orders", expects=">=1.0.0"),)),
            _orders(),
        ],
        today=TODAY,
    )

    only = _one(findings, "landscape/import-cycle")
    assert only.severity is Severity.ERROR
    assert only.message == "import cycle: design:payments -> design:orders -> design:payments"


def test_a_version_outside_the_range_the_importer_expects_is_an_error() -> None:
    """Either the other side moved under us or our range is stale, and both
    are edits somebody has to make. Inside the range, nothing is said."""

    mismatched = check_landscape([_payments(), _orders(expects=">=2.0.0")], today=TODAY)
    agreeing = check_landscape([_payments(), _orders(expects=">=1.0.0,<2")], today=TODAY)

    only = _one(mismatched, "landscape/version-mismatch")
    assert only.severity is Severity.ERROR
    assert only.ref == "design:orders"
    assert only.message == "design:orders expects >=2.0.0 of design:payments, which is 1.2.0"

    assert _under(agreeing, "landscape/version-mismatch") == []


def test_a_range_nothing_can_parse_is_reported_as_unreadable_not_as_a_mismatch() -> None:
    """Not a judgement about the design: nothing can be compared until both
    sides write it in a form that reads the same way, and calling that a
    mismatch would send somebody to change the wrong number."""

    findings = check_landscape([_payments(), _orders(expects="whatever is newest")], today=TODAY)

    only = _one(findings, "landscape/version-unreadable")
    assert only.severity is Severity.WARN
    assert only.ref == "design:orders"
    assert "whatever is newest" in only.message
    assert _under(findings, "landscape/version-mismatch") == []


def test_one_element_id_defined_by_two_designs_is_an_error_naming_both() -> None:
    """A ref carries no location, which is what lets an element move without
    breaking a link; the price is that an id must be unique across everything
    indexed together."""

    findings = check_landscape(
        [
            _payments(components=(_component("component:shared", "Theirs"),)),
            _orders(components=(_component("component:shared", "Ours"),)),
        ],
        today=TODAY,
    )

    only = _one(findings, "landscape/duplicate-id")
    assert only.severity is Severity.ERROR
    assert only.ref == "component:shared"
    assert only.message == "component:shared is defined by design:payments and design:orders"


def test_an_export_nobody_consumes_is_information_and_only_once_somebody_imports() -> None:
    """A surface with no consumer is cost with no benefit, and it is the
    cheapest thing in a design to withdraw — but only once another design
    depends on it. Until then an unused export is a design nobody uses yet,
    which is not a smell."""

    consumed = check_landscape([_payments(), _orders()], today=TODAY)
    unused = check_landscape([_payments(), _orders(consumes=False)], today=TODAY)
    alone = check_landscape([_payments()], today=TODAY)

    assert _under(consumed, "landscape/export-unused") == []
    assert _under(alone, "landscape/export-unused") == []
    only = _one(unused, "landscape/export-unused")
    assert only.severity is Severity.INFO
    assert only.ref == "interface:charges"
    assert only.message == "design:payments exports interface:charges, which nothing consumes"


def test_each_designs_own_findings_are_reported_under_its_id() -> None:
    """The landscape run folds every design's `check` into one report, so a
    message that named only an element would leave a reader guessing which
    design it came from. The rule ids stay the per-design ones: the landscape
    layer adds questions, it does not re-grade the answers."""

    findings = check_landscape([_payments(), _orders(consumes=False)], today=TODAY)

    unserved = [found for found in findings if found.rule_id == "policy/goal-unserved"]
    assert unserved == []
    assert all(
        found.message.startswith(("design:payments: ", "design:orders: "))
        for found in findings
        if not found.rule_id.startswith("landscape/")
    )
