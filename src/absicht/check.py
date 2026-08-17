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
handled upstream, for ``--explain`` to answer with. Notes stay outside that
walk by construction — they are not in the ``Design`` — and their single
rule reads the loader's collection instead.

The policy layer passes judgement on the same resolved artifact — states,
staleness and accountability rather than structure. Its severities are a
posture, not a fact: the unowned ``unknown`` and the rationale-less
``one_way`` decision are errors because the spec's own wording is "needs",
while the unrealized requirement and the expired external assumption are
warnings — incomplete-but-honest and stale-but-routine are the states
``observed``-heavy brownfield stores legitimately hold, and a checker that
errors on them teaches people to stop recording them. The clock is injected
(``today`` is a parameter, never read inside a rule), so a run answers
"expired as of when" and stays reproducible. The CLI wiring — flags,
formats, exit codes — is task 15's.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from graphlib import CycleError, TopologicalSorter

from absicht.findings import RULES, Finding, Severity, finding
from absicht.load import LoadedStore, LoadErrorReason
from absicht.models import Design, External, Ref, Reversibility, State
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
        "integrity/note-promoted-to-unresolvable": (
            "A note's promoted_to names the element it became, and that element "
            "must exist: the promotion is a note's one claim on the record, and a "
            "target no element defines leaves it pointing at something nobody can "
            "read. Always an error. This is the only rule that reads notes — they "
            "are outside the Design and exempt from graph validation by "
            "construction, so their refs are never walked; only a claimed "
            "promotion must resolve."
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


def note_findings(loaded: LoadedStore, index: Index) -> tuple[Finding, ...]:
    """The one rule that reads notes: a ``promoted_to`` no element defines.

    Notes never join ``iter_references`` — the exemption is structural, not a
    filter — so this walks the loader's own collection against the index.
    ``index`` must be ``Index.from_design`` of the store these notes loaded
    from, the same pairing every other layer here holds.
    """
    return tuple(
        finding(
            "integrity/note-promoted-to-unresolvable",
            severity=Severity.ERROR,
            message=(
                f"{note.id} is promoted to {note.promoted_to}, "
                "which no element in the store defines"
            ),
            ref=note.id,
            source=note.source or None,
        )
        for note in loaded.notes
        if note.promoted_to is not None and note.promoted_to not in index.by_id
    )


# --- the policy layer --------------------------------------------------------

RULES.update(
    {
        "policy/unknown-needs-owner": (
            "An element in state unknown must name an owner. Error, not warn: "
            "unknown means ask, spike or mark blocking — never invent — and with "
            "nobody accountable there is nobody to ask, which makes this a real "
            "gap rather than an incomplete-but-honest state."
        ),
        "policy/requirement-needs-realizer": (
            "A requirement must be realized by at least one component "
            "(realized_by). Warn, not error: a requirement still waiting for its "
            "realizer is incomplete but honest — the state brownfield stores "
            "legitimately hold — so the finding nudges rather than blocks. It "
            "asks for a realizing component, not for the requirement's removal."
        ),
        "policy/one-way-needs-rationale": (
            "A one_way decision must carry a rationale body; whitespace is not "
            "one. Error, not warn: the spec's wording is 'needs a rationale "
            "body', and the argument is the point of a decision that cannot be "
            "revisited — once the door is closed, the why is the only thing "
            "anyone can still read."
        ),
        "policy/external-assumptions-expired": (
            "An external's expires_on is in the past relative to the run's "
            "today: the assumptions were verified only until then, so re-check "
            "before trusting them. Warn, not error: expiry is staleness about a "
            "third party, not a break in the design — re-checking is routine "
            "maintenance, and erroring would teach deleting the date."
        ),
    }
)

# Considered and declined, per the policy spec's own "optional extensions"
# clause. An overdue unresolved Question and a Milestone.unresolved entry a
# decision has already resolved_by are not rules: a Question that is unknown
# and unowned is already caught by policy/unknown-needs-owner, and neither
# overdue-ness nor staleness has a spec line to hang a rule id from — add them
# when one does. Orphaned elements (nothing points at them) are likewise not
# a finding: neither the integrity nor the policy spec models them, the same
# concern under two rule ids is exactly what the specs warn against, and
# `ab list --orphaned` / `ab gaps` already answer it as a query.


def policy_findings(design: Design, index: Index, *, today: date) -> tuple[Finding, ...]:
    """The four policy rules, in the order the spec lists them.

    ``index`` must be ``Index.from_design(design)``: the unknown-owner rule
    walks ``index.by_id`` — the one enumeration of every element — so a
    mismatched pair would judge a different design than the one handed in.
    ``today`` anchors the expiry rule and is injected rather than read from
    the clock, so runs are reproducible and a future ``--rev`` run can ask
    "expired as of when" without a rewrite.
    """
    return (
        *_unknown_needs_owner_findings(index),
        *_requirement_needs_realizer_findings(design),
        *_one_way_needs_rationale_findings(design),
        *_external_assumptions_expired_findings(design, today=today),
    )


def _unknown_needs_owner_findings(index: Index) -> tuple[Finding, ...]:
    """Every element — not only questions — that is ``unknown`` and unowned.

    Error: the README's posture for ``unknown`` is "ask, spike, or mark
    blocking; never invent", and an unknown with nobody accountable for it is
    a question nobody will ever ask.
    """
    return tuple(
        finding(
            "policy/unknown-needs-owner",
            severity=Severity.ERROR,
            message=f"{element.id} is unknown and has no owner",
            ref=element.id,
            # The loader-set store path; None for elements that never had one.
            source=element.source or None,
        )
        for element in index.by_id.values()
        if element.state is State.UNKNOWN and element.owner is None
    )


def _requirement_needs_realizer_findings(design: Design) -> tuple[Finding, ...]:
    """A requirement no component realizes — unconditionally, for now.

    The spec line carries no state carve-out ("a requirement needs a realizing
    component"), so none is implemented: an ``unknown`` requirement that is
    also unrealized is honest about being early, and the warn severity is
    what keeps that honesty from reading as breakage. If the fixtures ever
    show this as wrong noise rather than a fair nudge, the carve-out is the
    change to make — not before then.
    """
    return tuple(
        finding(
            "policy/requirement-needs-realizer",
            severity=Severity.WARN,
            message=f"{requirement.id} is realized by no component",
            ref=requirement.id,
            source=requirement.source or None,
        )
        for requirement in design.requirements
        if not requirement.realized_by
    )


def _one_way_needs_rationale_findings(design: Design) -> tuple[Finding, ...]:
    """A ``one_way`` decision whose body carries no argument.

    Error: reversibility is what earns it — a decision that cannot be
    revisited and cannot be explained is a gap nobody can repair later,
    because later is exactly what ``one_way`` forecloses. Decisions cheap or
    costly to revisit may go unexplained without a finding.
    """
    return tuple(
        finding(
            "policy/one-way-needs-rationale",
            severity=Severity.ERROR,
            message=f"{decision.id} is a one_way decision with no rationale body",
            ref=decision.id,
            source=decision.source or None,
        )
        for decision in design.decisions
        if decision.reversibility is Reversibility.ONE_WAY and not decision.body.strip()
    )


def expired_externals(design: Design, *, today: date) -> tuple[External, ...]:
    """Externals whose ``expires_on`` is strictly past the injected ``today``.

    The one spelling of "expired": ``ab gaps``' worklist reuses it rather than
    re-deriving the comparison, so the checker's finding and the worklist's
    entry can never disagree about when trust in an assumption lapses.
    """
    return tuple(
        external
        for external in design.externals
        if external.expires_on is not None and external.expires_on < today
    )


def _external_assumptions_expired_findings(design: Design, *, today: date) -> tuple[Finding, ...]:
    """An external whose assumptions were verified only until ``expires_on``,
    with that day strictly in the past relative to the injected ``today``.

    Strictly: ``expires_on`` means "after this, re-check", so the day itself
    is still within what was verified. Warn: staleness about a third party is
    routine maintenance, not a break in the design.
    """

    def as_finding(external: External) -> Finding:
        # The non-None `expires_on` is guaranteed by `expired_externals`' own
        # filter, out of the type checker's sight — narrowed here rather than
        # trusted.
        assert external.expires_on is not None
        return finding(
            "policy/external-assumptions-expired",
            severity=Severity.WARN,
            message=(
                f"{external.id}'s assumptions expired on {external.expires_on.isoformat()}"
                " — re-check before trusting"
            ),
            ref=external.id,
            source=external.source or None,
        )

    return tuple(as_finding(external) for external in expired_externals(design, today=today))
