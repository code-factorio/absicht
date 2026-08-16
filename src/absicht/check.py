"""``ab check``'s first two layers: schema findings, then integrity findings.

The schema layer is the one with the least new logic to write: pydantic
already enforced the field types and the ``Ref``/``Slug``/``CriterionId``
patterns at parse time, inside ``absicht.codec``/``absicht.load``, and every
file that failed there is already a ``LoadError``. What this module adds is
the translation ``load`` deliberately does not do — one ``LoadError`` becomes
one ``Finding`` at error severity, under a rule id that says which *kind* of
schema problem it was, because ``ab check --explain ID`` answers "what does
this rule check" per rule, not per file.

The integrity layer reads the resolved artifact instead of the load errors:
every reference a ``Design`` carries must name an element that exists, and
the two relations that must be acyclic — ``contains`` and ``depends_on`` —
are checked as their own directed graphs. Criteria anchoring is the spec's
third integrity line but cannot be violated here: ``Story``'s own validator
rejects a misanchored criterion at parse time, so it can only ever surface
as a ``schema/validation`` load error; its id stays registered, marked
handled upstream, for ``--explain`` to answer with.

The policy layer lands in this same module (task 14); the CLI wiring —
flags, formats, exit codes — is task 15's.
"""

from __future__ import annotations

from collections.abc import Iterator
from graphlib import CycleError, TopologicalSorter

from absicht.findings import RULES, Finding, Severity, finding
from absicht.load import LoadedStore, LoadErrorReason
from absicht.models import Design, Ref
from absicht.resolve import Index, iter_references

RULES.update(
    {
        "schema/yaml-syntax": (
            "A file that is not the format: YAML the parser refuses, or a document "
            "without the --- front matter every element is read through. Always an "
            "error — a file that does not parse cannot be advisory."
        ),
        "schema/validation": (
            "A file that parsed but whose fields failed validation: a wrong type, a "
            "Ref/Slug/CriterionId pattern, or a record-level rule such as a criterion "
            "anchored to another story. The message names the offending field."
        ),
        "schema/system-missing": (
            "The store has no system.yaml. A store is exactly one System element plus "
            "its kind directories, and everything downstream reads the system."
        ),
        "schema/unreadable-file": (
            "A file the loader could not read at all — permissions, or it vanished "
            "mid-walk. Not a judgement about the design, but check cannot see past a "
            "file it cannot read."
        ),
        "integrity/dangling-ref": (
            "A ref-typed field points at an id no element in the store defines. Refs "
            "are typed `kind:slug` precisely so this is checkable without a lookup, "
            "and a dangling ref is a link that stops tracing — in System.externals "
            "and a criterion's touches as much as in contains. The finding names the "
            "source element, the field, and the missing target. Always an error."
        ),
        "integrity/cycle": (
            "A relation that must be acyclic has a cycle: contains (component "
            "nesting) or depends_on (milestone ordering), each checked as its own "
            "directed graph. One finding per distinct cycle, naming every element "
            "on it — a cycle leaves `inside` and `before` undefined. Always an error."
        ),
        # The spec's third integrity line — criteria anchored to their story —
        # is unreachable here by construction: Story._criteria_anchored_to_story
        # in models.py rejects a misanchored criterion at parse time, so it only
        # ever surfaces as a schema/validation load error. Registered as handled
        # upstream rather than silently dropped, so --explain answers for it.
        "integrity/criteria-anchored": (
            "Handled upstream, at the schema layer: Story's own validator rejects a "
            "criterion anchored to another story at parse time, and the failure "
            "surfaces as schema/validation on that story's file. No integrity "
            "finding can carry this id."
        ),
    }
)

_RULE_BY_REASON: dict[LoadErrorReason, str] = {
    LoadErrorReason.SYNTAX: "schema/yaml-syntax",
    LoadErrorReason.VALIDATION: "schema/validation",
    LoadErrorReason.MISSING_SYSTEM: "schema/system-missing",
    LoadErrorReason.IO: "schema/unreadable-file",
}
"""One rule id per failure family — the reason exists so this is a lookup, not message parsing."""


def schema_findings(loaded: LoadedStore) -> tuple[Finding, ...]:
    """One error-severity finding per ``LoadError``, in the order load reported them."""
    return tuple(
        finding(
            _RULE_BY_REASON[error.reason],
            severity=Severity.ERROR,
            message=error.message,
            source=error.path,
        )
        for error in loaded.errors
    )


def integrity_findings(design: Design, index: Index) -> tuple[Finding, ...]:
    """Every dangling ref, then every cycle in ``contains`` or ``depends_on``.

    ``index`` must be ``Index.from_design(design)``: the same enumeration that
    built the index decides what "exists" means here, so a mismatched pair
    would misreport both rules. Dangling refs come first, in ``Design`` field
    order; cycles after, one finding per distinct cycle.
    """
    return (
        *_dangling_ref_findings(design, index),
        *_cycle_findings(design, index),
    )


def _dangling_ref_findings(design: Design, index: Index) -> tuple[Finding, ...]:
    """One finding per reference whose target no element defines.

    ``iter_references`` is the one enumeration of ref-typed fields — the walk
    ``Index`` itself is built from — so a field added to a model is checked
    here without this module learning about it, criteria ``touches`` included
    (attributed to the story that carries them) and ``System.externals`` too,
    which is why the multi-repo sanity the spec asks about needs no rule of
    its own.
    """
    return tuple(
        finding(
            "integrity/dangling-ref",
            severity=Severity.ERROR,
            message=(
                f"{reference.source}'s {reference.field} points at "
                f"{reference.target}, which no element in the store defines"
            ),
            ref=reference.source,
            # The singleton system.yaml carries no store path; renderers treat
            # None and "" differently (SARIF emits a location for "").
            source=index.by_id[reference.source].source or None,
        )
        for reference in iter_references(design)
        if reference.target not in index.by_id
    )


def _cycle_findings(design: Design, index: Index) -> tuple[Finding, ...]:
    """One finding per distinct cycle, per relation, in ``Design`` field order.

    ``contains`` (component nesting) and ``depends_on`` (milestone ordering)
    are checked as separate directed graphs: each must be acyclic for
    "inside" and "before" to mean anything. A target that does not resolve is
    the dangling-ref rule's finding and cannot close a cycle, so it is
    dropped from the graph before the walk.
    """
    relations = (
        ("contains", tuple((c.id, c.contains) for c in design.components)),
        ("depends_on", tuple((m.id, m.depends_on) for m in design.milestones)),
    )
    findings: list[Finding] = []
    for relation, edges in relations:
        graph = {
            source: tuple(target for target in targets if target in index.by_id)
            for source, targets in edges
        }
        findings.extend(
            finding(
                "integrity/cycle",
                severity=Severity.ERROR,
                message=f"{relation} edges form a cycle: {' -> '.join(cycle)}",
            )
            for cycle in _cycles(graph)
        )
    return tuple(findings)


def _cycles(graph: dict[Ref, tuple[Ref, ...]]) -> Iterator[tuple[Ref, ...]]:
    """Every distinct cycle in a directed graph, as the closed path through it.

    ``TopologicalSorter.prepare`` raises ``CycleError`` once, naming one cycle
    in ``args[1]`` as the node path with its first node repeated at the end —
    the shape CPython's graphlib has always produced, and the reason it is
    preferred over a hand-rolled DFS here. Dropping that cycle's nodes and
    re-preparing finds cycles elsewhere in the graph, so disjoint loops are
    reported separately; cycles sharing a node surface as the one loop the
    first hit identifies, which is one finding for what is already an error
    either way.
    """
    remaining = graph
    while remaining:
        try:
            TopologicalSorter(remaining).prepare()
        except CycleError as exc:
            cycle: list[Ref] = exc.args[1]
            members = set(cycle)
            remaining = {
                node: targets for node, targets in remaining.items() if node not in members
            }
            yield tuple(cycle)
        else:
            return
