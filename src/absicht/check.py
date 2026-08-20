"""Proposed `ab check` for the revamped model: integrity, then policy.

Two layers, and the split is the point.

*Integrity* asks whether the graph holds together — does every reference
resolve, is every relation legal, is anything acyclic that must be. These are
facts about the design, so every one of them is an error.

*Policy* passes judgement on the same graph: coverage, agency, staleness. Its
severities are a posture, not a fact. An unimplemented requirement and an
expired assumption are warnings, because incomplete-but-honest is a state a
brownfield design legitimately holds, and a checker that fails on it teaches
people to stop recording it. An `unknown` with no owner is an error, because
nobody can resolve it.

There is no schema layer here. Pydantic already rejected the malformed record
at parse time, so `codec` owns that translation. Rules that a model validator
enforces are registered all the same, marked handled upstream, so
`ab check --explain ID` answers for every rule we agreed.

The clock is a parameter. A rule never reads `date.today()`, so a run answers
"expired as of when" and stays reproducible.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date
from graphlib import CycleError, TopologicalSorter
from itertools import pairwise

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from absicht.findings import RULES, Finding, Severity, finding
from absicht.load import LoadedStore, LoadErrorReason
from absicht.models.design import (
    Behavior,
    Component,
    ComponentLevel,
    Design,
    ExternalService,
    Interface,
    Outcome,
    RelationshipType,
    State,
)
from absicht.resolve import Index, carriers, kind, references

RULES.update(
    {
        # --------------------------------------------------------------- store
        "store/yaml-syntax": (
            "A file does not read as the format at all: YAML the parser "
            "refuses, a document that is not a mapping, or front matter that "
            "never closes. Nothing downstream can run until it parses."
        ),
        "store/validation": (
            "A file parsed but its fields did not validate. Every shape a "
            "record cannot have surfaces here, because pydantic rejects it at "
            "the boundary rather than a rule re-deriving it later."
        ),
        "store/design-missing": (
            "No `design.yaml`. A store is one design, and a design without an "
            "id, a title and a version cannot be folded or pointed at."
        ),
        "store/unreadable-file": (
            "A file could not be read, never mind parsed. A permission or an "
            "encoding, not a design judgement."
        ),
        # ------------------------------------------------------------ integrity
        "integrity/dangling-ref": (
            "A ref-typed field points at an id nothing defines, here or in an "
            "imported design. Refs are typed `kind:slug` so this is checkable "
            "without a lookup, and a dangling ref is a trace that stops."
        ),
        "integrity/not-exported": (
            "A ref names an element an imported design defines but does not "
            "export. Reaching past the export surface makes the other design's "
            "internals your dependency, and neither side can move again."
        ),
        "integrity/export-undefined": (
            "An exported ref names nothing this design defines. You may export "
            "only what you declare: to offer somebody else's interface, wrap it "
            "in one of yours, which makes it yours to keep."
        ),
        "integrity/export-kind": (
            "Handled upstream: `Design`'s own validator rejects an export that "
            "is not a contract kind. A goal or a requirement is why we built "
            "the thing and a component is the thing, so neither crosses a "
            "boundary. It surfaces as a parse failure on design.yaml."
        ),
        "integrity/component-level": (
            "The C4 nesting rule: a system has no parent, a container's parent "
            "is a system, a component's parent is a container. Nesting is the "
            "zoom, so a broken chain makes every diagram wrong."
        ),
        "integrity/cycle": (
            "A relation that must be acyclic has one: component nesting, "
            "milestone order, or supersession. One finding per distinct cycle, "
            "naming every element on it, because a cycle leaves `inside`, "
            "`before` and `replaces` undefined."
        ),
        "integrity/edge-kinds": (
            "A relationship joins two kinds it is not defined between — a "
            "`calls` edge into a library, an `implements` edge from something "
            "that is not a component. The edge kind is what a checker branches "
            "on, so a wrong one silently disables every rule behind it."
        ),
        "integrity/observation-target": (
            "An observation's `at` points at something you cannot observe. A "
            "component, an interface, a resource or another behavior can be "
            "watched; a requirement, a goal or a decision cannot."
        ),
        "integrity/must-not-has-timing": (
            "Handled upstream: `Observation`'s validator rejects a `must_not` "
            "that carries a `timing`, because `must_not` means at no point and "
            "a timing says when the never happens."
        ),
        "integrity/observations-anchored": (
            "Handled upstream: `Behavior`'s validator rejects an observation "
            "whose id names another behavior. The id says which behavior owns "
            "it, so a mismatch is a broken file and not a design judgement."
        ),
        "integrity/external-design-unknown": (
            "An external service names a design that no import declares. The "
            "box has to point at something we actually pulled in, or the "
            "contract behind it cannot be read."
        ),
        "integrity/external-design-interface": (
            "An interface is declared by an external service that has its own "
            "design. Their exports are the contract; a copy here would be a "
            "second opinion about something somebody else publishes."
        ),
        "integrity/interface-on-resource": (
            "An interface is declared by a resource. A resource takes part in "
            "no contract: a component's relation to one is a dependency, and "
            "the observations pointing at it are what give it meaning."
        ),
        "integrity/repository-unknown": (
            "An `implemented_by` entry uses a repository prefix that "
            "`Design.repositories` does not declare, so the link into code "
            "resolves to a guess instead of to a URL and a ref."
        ),
        # --------------------------------------------------------------- policy
        "policy/requirement-unimplemented": (
            "No component implements this requirement. An error once a human "
            "has reviewed it, because somebody agreed to build it and nothing "
            "claims to; a warning while it is still assumed."
        ),
        "policy/requirement-unrealized": (
            "No behavior realizes this requirement, so nothing says how you "
            "would know it holds. A warning: the requirement may be true and "
            "merely unobserved, which is a normal state mid-design."
        ),
        "policy/requirement-aimless": (
            "The requirement derives from no goal, so nobody can say why it "
            "exists. A warning, because the goal may simply not be written yet."
        ),
        "policy/goal-unserved": (
            "No requirement derives from this goal. An error: a goal nothing "
            "serves is either finished, abandoned, or a slogan, and each of "
            "those wants a different edit."
        ),
        "policy/goal-unmeasured": (
            "The goal states no measure, so nobody can tell whether it was "
            "met. A goal with no measure is a slogan."
        ),
        "policy/behavior-unobserved": (
            "A behavior with no observations says something happens and never "
            "says what, so verification has nothing to check."
        ),
        "policy/agency-undeclared": (
            "A `constrained` or `delegated` element carries no "
            "`reversibility`, so an agent cannot judge whether to decide "
            "freely, propose first, or stop and ask."
        ),
        "policy/unknown-unowned": (
            "An `unknown` element has no owner. `unknown` means ask, and an "
            "error here is the honest one: with nobody to ask, the state is a "
            "wish and an agent will invent instead."
        ),
        "policy/assumption-expired": (
            "An assumption passed `expires_on`. Stale-but-routine, so a "
            "warning — but everything in `invalidates` is now unproven."
        ),
        "policy/external-assumption-expired": (
            "An external service passed `expires_on`. Somebody else's system "
            "moved while we were not looking, or nobody re-checked."
        ),
        "policy/import-unpinned": (
            "An import states no `expects`, so nothing can warn when the other "
            "design moves under us. The same gap as a dependency with no "
            "version range."
        ),
        "policy/quality-unevidenced": (
            "A component claims to satisfy a quality requirement that carries "
            "no evidence. The claim may be true; nothing measured it."
        ),
        "policy/milestone-unscoped": (
            "A milestone declares no `scope`, so nothing says what an agent "
            "may touch. The packet cannot be assembled from it."
        ),
        "policy/note-dangling": (
            "A note points at an element nothing defines. Informational and "
            "never a failure: a note about something not yet written is the "
            "normal case, and the point of the typed link is that a rename "
            "surfaces it."
        ),
        "policy/advisory-count": (
            "How many `should` observations exist. They never fail "
            "verification, which is what makes them a dumping ground, so the "
            "count is reported to keep it visible."
        ),
        # ----------------------------------------------------------- landscape
        "landscape/duplicate-design": (
            "Two designs claim the same id. Every ref resolves against one "
            "index built from the whole landscape, so a repeated design id "
            "makes every foreign lookup ambiguous."
        ),
        "landscape/import-unresolved": (
            "A design imports one the landscape does not hold. Nothing after "
            "it can be trusted for that design: every ref into the missing "
            "design reads as dangling, which is the honest cascade."
        ),
        "landscape/import-cycle": (
            "Two or more designs import each other. Two designs that need each "
            "other are one design, and neither can be released without the "
            "other."
        ),
        "landscape/version-mismatch": (
            "An imported design's version falls outside the range the importer "
            "expects. Either the other side moved under us or our range is "
            "stale, and both are edits somebody has to make."
        ),
        "landscape/version-unreadable": (
            "A version or a range that cannot be parsed. Not a judgement about "
            "the design, but nothing can be compared until both sides write it "
            "in a form that reads the same way."
        ),
        "landscape/duplicate-id": (
            "Two designs define the same element id. A ref carries no "
            "location, which is what lets an element move without breaking a "
            "link; the price is that an id must be unique across everything "
            "indexed together."
        ),
        "landscape/export-unused": (
            "A design that others import exports something nobody consumes. "
            "Informational: a surface with no consumer is cost with no "
            "benefit, and it is the cheapest thing in a design to withdraw."
        ),
    }
)


# ---------------------------------------------------------------------- store


_LOAD_RULES: dict[LoadErrorReason, str] = {
    LoadErrorReason.SYNTAX: "store/yaml-syntax",
    LoadErrorReason.VALIDATION: "store/validation",
    LoadErrorReason.MISSING_DESIGN: "store/design-missing",
    LoadErrorReason.IO: "store/unreadable-file",
}


def store_findings(loaded: LoadedStore) -> list[Finding]:
    """The files that did not load, as findings.

    The one layer above the design graph: a file nobody could parse is not a
    statement about the design, so no rule here reads a `Design`. `load`
    already classified each failure, which is why this is a lookup and not a
    second reading of the message.
    """
    return [
        finding(
            _LOAD_RULES[error.reason],
            severity=Severity.ERROR,
            message=error.message,
            source=error.path,
        )
        for error in loaded.errors
    ]


# ------------------------------------------------------------------ integrity


def _refs_resolve(ix: Index) -> Iterator[Finding]:
    for element in ix.elements():
        for carrier in carriers(element):
            owner = getattr(carrier, "id", element.id)
            for field, ref in references(carrier):
                if ix.resolves(ref):
                    continue
                rule = (
                    "integrity/not-exported"
                    if ix.is_private_foreign(ref)
                    else "integrity/dangling-ref"
                )
                yield finding(
                    rule,
                    severity=Severity.ERROR,
                    message=f"{owner}.{field} points at {ref}",
                    ref=element.id,
                    source=element.source or None,
                )
    for edge in ix.design.relationships:
        for field, ref in (("source_id", edge.source_id), ("target_id", edge.target_id)):
            if ix.resolves(ref):
                continue
            rule = (
                "integrity/not-exported" if ix.is_private_foreign(ref) else "integrity/dangling-ref"
            )
            yield finding(
                rule,
                severity=Severity.ERROR,
                message=f"{edge.type} edge {field} points at {ref}",
                ref=edge.source_id,
            )


def _exports_defined(ix: Index) -> Iterator[Finding]:
    for ref in ix.design.exports:
        if ref not in ix.local:
            yield finding(
                "integrity/export-undefined",
                severity=Severity.ERROR,
                message=f"{ix.design.id} exports {ref}, which it does not define",
                ref=ix.design.id,
            )


_PARENT_OF: dict[ComponentLevel, ComponentLevel | None] = {
    ComponentLevel.SYSTEM: None,
    ComponentLevel.CONTAINER: ComponentLevel.SYSTEM,
    ComponentLevel.COMPONENT: ComponentLevel.CONTAINER,
}


def _component_levels(ix: Index) -> Iterator[Finding]:
    for component in ix.of_type(Component):
        expected = _PARENT_OF[component.level]
        parent = ix.local.get(component.parent) if component.parent else None
        if expected is None:
            if component.parent:
                yield finding(
                    "integrity/component-level",
                    severity=Severity.ERROR,
                    message=f"{component.id} is a system and has a parent",
                    ref=component.id,
                    source=component.source or None,
                )
            continue
        if parent is None:
            yield finding(
                "integrity/component-level",
                severity=Severity.ERROR,
                message=f"{component.id} is a {component.level} with no parent {expected}",
                ref=component.id,
                source=component.source or None,
            )
        elif not isinstance(parent, Component) or parent.level is not expected:
            yield finding(
                "integrity/component-level",
                severity=Severity.ERROR,
                message=f"{component.id} is a {component.level}; its parent must be a {expected}",
                ref=component.id,
                source=component.source or None,
            )


def _break_edge(working: dict[str, set[str]], cycle: Sequence[str]) -> bool:
    """Drop one edge of a reported cycle, so the next pass finds the next one.

    Which way round `graphlib` lists the path is its business, so try both;
    returning False when nothing came out is what stops the caller looping
    forever on an edge it cannot find.
    """
    for first, second in pairwise(cycle):
        for tail, head in ((first, second), (second, first)):
            if head in working.get(tail, ()):
                working[tail].discard(head)
                return True
    return False


def _acyclic(
    graph: Mapping[str, set[str]],
    label: str,
    rule_id: str = "integrity/cycle",
) -> Iterator[Finding]:
    """Report every distinct cycle, not only the first one graphlib names."""
    working = {node: set(edges) for node, edges in graph.items()}
    while True:
        try:
            TopologicalSorter(working).prepare()
            return
        except CycleError as exc:
            nodes = list(exc.args[1])
            yield finding(
                rule_id,
                severity=Severity.ERROR,
                message=f"{label} cycle: {' -> '.join(nodes)}",
                ref=nodes[0],
            )
            if not _break_edge(working, nodes):
                return


def _cycles(ix: Index) -> Iterator[Finding]:
    nesting = {c.id: {c.parent} if c.parent else set() for c in ix.of_type(Component)}
    yield from _acyclic(nesting, "component nesting")

    order: dict[str, set[str]] = {}
    for source, target in ix.edges(RelationshipType.DEPENDS_ON):
        order.setdefault(source, set()).add(target)
    yield from _acyclic(order, "depends_on")

    supersession = {e.id: set(e.supersedes) for e in ix.elements() if e.supersedes}
    yield from _acyclic(supersession, "supersedes")


_ANY: frozenset[str] | None = None

_EDGE_KINDS: dict[RelationshipType, tuple[frozenset[str] | None, frozenset[str] | None]] = {
    RelationshipType.IMPLEMENTS: (frozenset({"component"}), frozenset({"req", "interface"})),
    RelationshipType.SATISFIES: (frozenset({"component"}), frozenset({"quality"})),
    RelationshipType.CONSTRAINED_BY: (frozenset({"component"}), frozenset({"constraint"})),
    RelationshipType.REALIZES: (frozenset({"behavior"}), frozenset({"req"})),
    RelationshipType.CALLS: (
        frozenset({"component"}),
        frozenset({"interface", "external", "design"}),
    ),
    RelationshipType.DEPENDS_ON: (
        frozenset({"component"}),
        frozenset({"library", "resource", "component"}),
    ),
    RelationshipType.DERIVES_FROM: (frozenset({"req"}), frozenset({"req", "goal"})),
    RelationshipType.SPECIFIES: (frozenset({"design"}), _ANY),
    RelationshipType.REFINES: (_ANY, _ANY),
    RelationshipType.CONFLICTS_WITH: (_ANY, _ANY),
    RelationshipType.RELATES_TO: (_ANY, _ANY),
}


def _edge_kinds(ix: Index) -> Iterator[Finding]:
    for edge in ix.design.relationships:
        sources, targets = _EDGE_KINDS[edge.type]
        if sources is not None and kind(edge.source_id) not in sources:
            yield finding(
                "integrity/edge-kinds",
                severity=Severity.ERROR,
                message=f"{edge.type} starts at {edge.source_id}; it starts at {sorted(sources)}",
                ref=edge.source_id,
            )
        if targets is not None and kind(edge.target_id) not in targets:
            yield finding(
                "integrity/edge-kinds",
                severity=Severity.ERROR,
                message=f"{edge.type} ends at {edge.target_id}; it ends at {sorted(targets)}",
                ref=edge.source_id,
            )


_OBSERVABLE = frozenset({"component", "interface", "resource", "behavior"})


def _observation_targets(ix: Index) -> Iterator[Finding]:
    for behavior in ix.of_type(Behavior):
        for observation in behavior.observations:
            if kind(observation.at) not in _OBSERVABLE:
                yield finding(
                    "integrity/observation-target",
                    severity=Severity.ERROR,
                    message=f"{observation.id} watches {observation.at}, which cannot be watched",
                    ref=behavior.id,
                    source=behavior.source or None,
                )


def _boundaries(ix: Index) -> Iterator[Finding]:
    declared_designs = {imported.id for imported in ix.design.imports}
    backed: set[str] = set()
    for service in ix.design.external_services:
        if service.design is None:
            continue
        backed.add(service.id)
        if service.design not in declared_designs:
            yield finding(
                "integrity/external-design-unknown",
                severity=Severity.ERROR,
                message=f"{service.id} names {service.design}, which no import declares",
                ref=service.id,
                source=service.source or None,
            )
    for interface in ix.of_type(Interface):
        owner = interface.declared_by
        if owner is None:
            continue
        if owner in backed:
            yield finding(
                "integrity/external-design-interface",
                severity=Severity.ERROR,
                message=f"{interface.id} is declared by {owner}, which has its own design",
                ref=interface.id,
                source=interface.source or None,
            )
        if kind(owner) == "resource":
            yield finding(
                "integrity/interface-on-resource",
                severity=Severity.ERROR,
                message=f"{interface.id} is declared by the resource {owner}",
                ref=interface.id,
                source=interface.source or None,
            )


def _repositories(ix: Index) -> Iterator[Finding]:
    declared = {repository.id for repository in ix.design.repositories}
    for element in ix.elements():
        for entry in getattr(element, "implemented_by", ()):
            prefix = entry.split("#", 1)[0]
            if prefix not in declared:
                yield finding(
                    "integrity/repository-unknown",
                    severity=Severity.ERROR,
                    message=f"{element.id} points into the undeclared repository {prefix!r}",
                    ref=element.id,
                    source=element.source or None,
                )


# --------------------------------------------------------------------- policy


def _requirement_coverage(ix: Index) -> Iterator[Finding]:
    implemented = ix.targets_of(RelationshipType.IMPLEMENTS)
    realized = ix.targets_of(RelationshipType.REALIZES)

    for requirement in ix.design.requirements:
        if requirement.id not in implemented:
            reviewed = requirement.confidence is not requirement.confidence.ASSUMED
            yield finding(
                "policy/requirement-unimplemented",
                severity=Severity.ERROR if reviewed else Severity.WARN,
                message=f"nothing implements {requirement.id}",
                ref=requirement.id,
                source=requirement.source or None,
            )
        if requirement.id not in realized:
            yield finding(
                "policy/requirement-unrealized",
                severity=Severity.WARN,
                message=f"no behavior says how you would know {requirement.id} holds",
                ref=requirement.id,
                source=requirement.source or None,
            )
        goals = {t for s, t in ix.edges(RelationshipType.DERIVES_FROM) if s == requirement.id}
        if not any(kind(goal) == "goal" for goal in goals):
            yield finding(
                "policy/requirement-aimless",
                severity=Severity.WARN,
                message=f"{requirement.id} derives from no goal",
                ref=requirement.id,
                source=requirement.source or None,
            )


def _goal_coverage(ix: Index) -> Iterator[Finding]:
    derived_from = ix.targets_of(RelationshipType.DERIVES_FROM)

    for goal in ix.design.goals:
        if goal.id not in derived_from:
            yield finding(
                "policy/goal-unserved",
                severity=Severity.ERROR,
                message=f"no requirement serves {goal.id}",
                ref=goal.id,
                source=goal.source or None,
            )
        if not goal.measure:
            yield finding(
                "policy/goal-unmeasured",
                severity=Severity.WARN,
                message=f"{goal.id} states no measure",
                ref=goal.id,
                source=goal.source or None,
            )


def _evidence_coverage(ix: Index) -> Iterator[Finding]:
    """What a behavior, a quality and a milestone each owe before anyone builds."""
    evidenced = ix.targets_of(RelationshipType.SATISFIES)

    for behavior in ix.of_type(Behavior):
        if not behavior.observations:
            yield finding(
                "policy/behavior-unobserved",
                severity=Severity.ERROR,
                message=f"{behavior.id} observes nothing",
                ref=behavior.id,
                source=behavior.source or None,
            )

    for quality in ix.design.qualities:
        if quality.id in evidenced and not quality.evidence:
            yield finding(
                "policy/quality-unevidenced",
                severity=Severity.WARN,
                message=f"{quality.id} is claimed satisfied and carries no evidence",
                ref=quality.id,
                source=quality.source or None,
            )

    for milestone in ix.design.milestones:
        if not milestone.scope:
            yield finding(
                "policy/milestone-unscoped",
                severity=Severity.ERROR,
                message=f"{milestone.id} says nothing about what may be touched",
                ref=milestone.id,
                source=milestone.source or None,
            )


_DECIDES = frozenset({State.CONSTRAINED, State.DELEGATED})


def _agency(ix: Index) -> Iterator[Finding]:
    for element in ix.elements():
        if element.state in _DECIDES and element.reversibility is None:
            yield finding(
                "policy/agency-undeclared",
                severity=Severity.WARN,
                message=f"{element.id} is {element.state} and states no reversibility",
                ref=element.id,
                source=element.source or None,
            )
        if element.state is State.UNKNOWN and not element.owner:
            yield finding(
                "policy/unknown-unowned",
                severity=Severity.ERROR,
                message=f"{element.id} is unknown and has nobody to ask",
                ref=element.id,
                source=element.source or None,
            )


def expired_services(design: Design, *, today: date) -> tuple[ExternalService, ...]:
    """Every external service whose `expires_on` has passed.

    Here rather than in the caller because `ab gaps` puts the same fact on
    its worklist: one spelling of "expired", so a warning and a worklist row
    can never disagree about which services lapsed.
    """
    return tuple(
        service
        for service in design.external_services
        if service.expires_on and service.expires_on < today
    )


def _staleness(ix: Index, today: date) -> Iterator[Finding]:
    for assumption in ix.design.assumptions:
        if assumption.expires_on and assumption.expires_on < today:
            yield finding(
                "policy/assumption-expired",
                severity=Severity.WARN,
                message=f"{assumption.id} expired on {assumption.expires_on}",
                ref=assumption.id,
                source=assumption.source or None,
            )
    for service in expired_services(ix.design, today=today):
        yield finding(
            "policy/external-assumption-expired",
            severity=Severity.WARN,
            message=f"{service.id} was last checked before {service.expires_on}",
            ref=service.id,
            source=service.source or None,
        )


def _boundaries_policy(ix: Index) -> Iterator[Finding]:
    for imported in ix.design.imports:
        if not imported.expects:
            yield finding(
                "policy/import-unpinned",
                severity=Severity.WARN,
                message=f"{imported.id} is imported with no version range",
                ref=imported.id,
            )


def _notes(ix: Index) -> Iterator[Finding]:
    for note in ix.design.notes:
        for ref in note.about:
            if not ix.resolves(ref):
                yield finding(
                    "policy/note-dangling",
                    severity=Severity.INFO,
                    message=f"{note.id} is about {ref}, which nothing defines",
                    ref=note.id,
                )


def _advisory(ix: Index) -> Iterator[Finding]:
    advisory = [
        observation.id
        for behavior in ix.of_type(Behavior)
        for observation in behavior.observations
        if observation.outcome is Outcome.SHOULD
    ]
    if advisory:
        yield finding(
            "policy/advisory-count",
            severity=Severity.INFO,
            message=f"{len(advisory)} advisory observations never fail verification",
        )


# ---------------------------------------------------------------------- entry


def _worst_first(one: Finding) -> tuple[int, str, str]:
    return (-one.severity.rank, one.rule_id, one.ref or "")


def check(
    design: Design,
    *,
    imports: Mapping[str, Design] | None = None,
    today: date | None = None,
) -> list[Finding]:
    """Every finding about one design, worst first.

    `imports` carries the designs this one pulls in, keyed by design id. Pass
    none and every foreign ref reads as dangling, which is the honest answer
    when the other design was not fetched.
    """
    ix = Index(design, imports or {})
    when = today or date.today()
    produced: Iterable[Finding] = (
        *_refs_resolve(ix),
        *_exports_defined(ix),
        *_component_levels(ix),
        *_cycles(ix),
        *_edge_kinds(ix),
        *_observation_targets(ix),
        *_boundaries(ix),
        *_repositories(ix),
        *_requirement_coverage(ix),
        *_goal_coverage(ix),
        *_evidence_coverage(ix),
        *_agency(ix),
        *_staleness(ix, when),
        *_boundaries_policy(ix),
        *_notes(ix),
        *_advisory(ix),
    )
    return sorted(produced, key=_worst_first)


# ------------------------------------------------------------------ landscape


def _mentioned(design: Design) -> set[str]:
    """Every ref this design names, wherever it names it."""
    refs: set[str] = set()
    for element in design.elements():
        for carrier in carriers(element):
            refs.update(ref for _, ref in references(carrier))
    for edge in design.relationships:
        refs.update({edge.source_id, edge.target_id})
    return refs


def _versions_agree(design: Design, by_id: Mapping[str, Design]) -> Iterator[Finding]:
    for imported in design.imports:
        other = by_id.get(imported.id)
        if other is None or not imported.expects:
            continue
        try:
            allowed = SpecifierSet(imported.expects)
            actual = Version(other.version)
        except (InvalidSpecifier, InvalidVersion) as exc:
            yield finding(
                "landscape/version-unreadable",
                severity=Severity.WARN,
                message=f"{design.id} expects {imported.expects!r} of {imported.id}: {exc}",
                ref=design.id,
            )
            continue
        if actual not in allowed:
            yield finding(
                "landscape/version-mismatch",
                severity=Severity.ERROR,
                message=f"{design.id} expects {imported.expects} of {imported.id}, which is {other.version}",
                ref=design.id,
            )


def _unused_exports(
    by_id: Mapping[str, Design], consumers: Mapping[str, set[str]]
) -> Iterator[Finding]:
    imported_by_someone = {imported.id for design in by_id.values() for imported in design.imports}
    for design in by_id.values():
        if design.id not in imported_by_someone:
            continue  # nobody depends on it yet, so an unused surface is not a smell
        used: set[str] = set()
        for other_id, refs in consumers.items():
            if other_id != design.id:
                used |= refs
        for ref in design.exports:
            if ref not in used:
                yield finding(
                    "landscape/export-unused",
                    severity=Severity.INFO,
                    message=f"{design.id} exports {ref}, which nothing consumes",
                    ref=ref,
                )


def check_landscape(designs: Iterable[Design], *, today: date | None = None) -> list[Finding]:
    """Every finding about a graph of designs, worst first.

    It owns the questions one design cannot answer about itself: whether its
    imports exist, whether the versions agree, whether an id is unique across
    everything indexed together, and whether the graph is acyclic. Then it
    runs `check` per design with the imports resolved, so a single call
    answers for the whole landscape.
    """
    by_id: dict[str, Design] = {}
    findings: list[Finding] = []
    for design in designs:
        if design.id in by_id:
            findings.append(
                finding(
                    "landscape/duplicate-design",
                    severity=Severity.ERROR,
                    message=f"two designs claim {design.id}",
                    ref=design.id,
                )
            )
            continue
        by_id[design.id] = design

    graph: dict[str, set[str]] = {}
    for design in by_id.values():
        graph[design.id] = set()
        for imported in design.imports:
            if imported.id not in by_id:
                findings.append(
                    finding(
                        "landscape/import-unresolved",
                        severity=Severity.ERROR,
                        message=f"{design.id} imports {imported.id} from {imported.source!r}, which is not here",
                        ref=design.id,
                    )
                )
                continue
            graph[design.id].add(imported.id)
    findings += _acyclic(graph, "import", rule_id="landscape/import-cycle")

    seen: dict[str, str] = {}
    for design in by_id.values():
        for element in design.elements():
            first = seen.setdefault(element.id, design.id)
            if first != design.id:
                findings.append(
                    finding(
                        "landscape/duplicate-id",
                        severity=Severity.ERROR,
                        message=f"{element.id} is defined by {first} and {design.id}",
                        ref=element.id,
                        source=element.source or None,
                    )
                )

    consumers = {design.id: _mentioned(design) for design in by_id.values()}
    for design in by_id.values():
        findings += _versions_agree(design, by_id)
    findings += _unused_exports(by_id, consumers)

    for design in by_id.values():
        resolved = {i.id: by_id[i.id] for i in design.imports if i.id in by_id}
        for one in check(design, imports=resolved, today=today):
            findings.append(one.model_copy(update={"message": f"{design.id}: {one.message}"}))

    return sorted(findings, key=_worst_first)
