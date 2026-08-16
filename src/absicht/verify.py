"""``ab verify``: the sealed packet, the diff, the rules and their running.

``CONTEXT.md`` calls ``ab verify`` *"the entire premise of the project"* — the
one check that asks whether the code is the code that was asked for, not just
whether it is well-formed. This module is the frame around that question:
``docs/tasks/40-verify-core.md``'s scaffolding up front, then
``docs/tasks/41-verify-rules.md``'s seven rule bodies hanging off
``VERIFY_RULES`` and ``VerifyContext``, with the judgement calls the rule
spec leaves open written down beside them.

Two contracts worth naming out loud:

- **Offline.** A rule sees the sealed ``Packet``, the ``PacketLock`` beside
  it, and the implementing repos' own diffs — nothing else. No design store,
  no network: everything a rule needs was sealed into the packet precisely so
  verification can run in CI, in somebody else's repository. A rule that turns
  out to need more is a signal the packet's shape is missing a field, not
  license to reach back into a live store connection.
- **Failure vocabulary.** A broken invocation — no sealed packet to verify, an
  unreadable one, a ``--repo`` that is not a directory, a ``--diff-base`` that
  does not resolve, a rule id nothing registers — raises ``VerifyUsageError``
  for the CLI to map to ``ExitCode.USAGE``. Findings about the *change* are
  the rules' business, reported through ``absicht.findings.Report`` the same
  way ``ab check`` reports findings about a store.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from absicht.findings import RULES, Finding, Report, Severity, finding
from absicht.gherkin import scenario_digest
from absicht.git import GitError, changed_paths
from absicht.models import (
    Component,
    Decision,
    Element,
    Fidelity,
    Packet,
    PacketLock,
    Seam,
    State,
)
from absicht.runstore import RunResult


class VerifyUsageError(Exception):
    """A broken invocation. The CLI maps this to ``ExitCode.USAGE``."""


type VerifyRule = Callable[[VerifyContext], tuple[Finding, ...]]
"""One rule: everything it may look at is the context, what it says back is
findings — the shape ``absicht.check``'s layers have, against a different
input."""


VERIFY_RULES: dict[str, VerifyRule] = {}
"""The rules ``ab verify`` runs, by id, in registration order.

A plain dict, like ``absicht.findings.RULES``: a handful of rules is a lookup,
not a plugin system. Populated at the bottom of this module with the seven
bodies of ``docs/tasks/41-verify-rules.md``, in that spec's own order; each
rule's ``--explain`` text registers in ``findings.RULES`` like every other
rule-producing module's."""


@dataclass(frozen=True, slots=True)
class VerifyContext:
    """Everything a rule may look at, and nothing more.

    ``changed`` holds, per repo, the paths changed since ``diff_base`` —
    relative to that repo's own root, the shape ``git.changed_paths`` returns
    and the one component ``implemented_by`` prefixes compare against.
    """

    packet: Packet
    lock: PacketLock
    diff_base: str
    repos: tuple[Path, ...]
    changed: Mapping[Path, frozenset[Path]]


def load_sealed_packet(path: Path) -> tuple[Packet, PacketLock]:
    """Read the sealed packet whose ``packet.lock`` is ``path``.

    ``path`` names the ``packet.lock`` — the file that makes a packet sealed,
    and the one the default discovery hands out — and the body read is its
    ``packet.json`` sibling: the one format that round-trips into the
    ``Packet`` model. A body sealed ``--format md`` is for humans and cannot
    be read back; refusing it with the fix named is better than a Markdown
    parser nobody wants. Two file reads, no store, no network — the offline
    contract starts here.
    """
    if not path.is_file():
        raise VerifyUsageError(
            f"{path}: no sealed packet there — seal one with ab packet MILESTONE --seal"
        )
    try:
        lock = PacketLock.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as exc:  # ValidationError is a ValueError; a corrupt lock is a usage error
        raise VerifyUsageError(f"{path}: not a readable packet.lock: {exc}") from exc
    body = path.parent / "packet.json"
    if not body.is_file():
        raise VerifyUsageError(
            f"{body}: a packet sealed --format md cannot be read back; "
            "seal with --format json for ab verify"
        )
    try:
        packet = Packet.model_validate_json(body.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise VerifyUsageError(f"{body}: not a readable packet body: {exc}") from exc
    return packet, lock


def discover_sealed_packet(packets_dir: Path) -> Path:
    """The one sealed packet under ``packets_dir``, or a refusal to guess.

    ``ab verify`` takes no milestone argument, so "the sealed packet in the
    build dir" can only mean: exactly one ``packet.lock`` under the packets
    dir. Zero or several is the caller's decision to make, not this command's
    — a silent pick would verify the wrong milestone and report it as a pass.
    """
    candidates = sorted(packets_dir.glob("*/packet.lock"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise VerifyUsageError(
            f"no sealed packet under {packets_dir}: seal one with ab packet "
            "MILESTONE --seal, or pass --packet PATH"
        )
    listed = ", ".join(str(candidate) for candidate in candidates)
    raise VerifyUsageError(
        f"{len(candidates)} sealed packets under {packets_dir}: "
        f"pass --packet PATH to choose one ({listed})"
    )


def context_for(
    packet: Packet,
    lock: PacketLock,
    *,
    diff_base: str,
    repos: Iterable[Path],
) -> VerifyContext:
    """The context for a run: the sealed pair plus each repo's diff.

    One diff per ``--repo``, each against the same ``diff_base``: a
    multi-repo slice is several working trees judged together, and flattening
    their diffs into one set would lose which repo a path belongs to.
    Repeating a ``--repo`` costs nothing (first spelling wins). A git read
    that fails surfaces as ``VerifyUsageError`` naming the repo and the base —
    a base that does not resolve is a broken invocation, not a finding.
    """
    resolved = tuple(dict.fromkeys(repos))
    changed: dict[Path, frozenset[Path]] = {}
    for repo in resolved:
        if not repo.is_dir():
            raise VerifyUsageError(f"--repo {repo}: no such directory")
        try:
            changed[repo] = changed_paths(diff_base, repo)
        except GitError as exc:
            raise VerifyUsageError(
                f"--diff-base {diff_base!r} against --repo {repo}: {exc}"
            ) from exc
    return VerifyContext(
        packet=packet, lock=lock, diff_base=diff_base, repos=resolved, changed=changed
    )


def run_rules(
    ctx: VerifyContext,
    *,
    include: frozenset[str] | None = None,
    exclude: frozenset[str] = frozenset(),
) -> Report:
    """Run the registered rules over ``ctx``, the selection applied first.

    Filtering the rule list rather than the findings afterwards is the point:
    an excluded rule never runs at all. An id nothing registers is a usage
    error — in the CI jobs verify is built for, a typo silently running
    nothing would exit 0 and call that a pass.
    """
    asked = (include if include is not None else frozenset()) | exclude
    if unknown := sorted(asked - VERIFY_RULES.keys()):
        raise VerifyUsageError(
            f"unknown rule {', '.join(unknown)}: "
            f"known rules are {', '.join(sorted(VERIFY_RULES)) or 'none yet'}"
        )
    selected = [
        rule
        for rule_id, rule in VERIFY_RULES.items()
        if (include is None or rule_id in include) and rule_id not in exclude
    ]
    return Report(findings=tuple(finding for rule in selected for finding in rule(ctx)))


def criterion_results(ctx: VerifyContext) -> tuple[RunResult, ...]:
    """The packet's criteria as one run-store row each, for ``absicht.runstore``.

    ``checked`` with the first file that references the id as evidence,
    ``no_check`` when nothing does — ``verify/done-when``'s own evidence walk,
    read as results rather than findings, so the record and the report cannot
    disagree about what a run verified. Computed from the context alone, not
    from the findings: a run with ``--rule`` narrowed still records every
    criterion's result. Observations join this table in
    docs/tasks/59-verify-observations.md, on the same evidence mechanism.
    """
    sources = sorted(_step_sources(ctx).items())
    results: list[RunResult] = []
    for criterion in ctx.packet.criteria:
        evidence = next(
            (path.as_posix() for (_repo, path), hits in sources if criterion.id in hits),
            None,
        )
        results.append(
            RunResult(
                criterion=criterion.id,
                result="no_check" if evidence is None else "checked",
                evidence_ref=evidence,
            )
        )
    return tuple(results)


# --- the rules (docs/tasks/41-verify-rules.md) ---------------------------------
#
# The judgement calls the rule spec leaves open, written down once so they are
# not re-litigated per bug report:
#
# - **What maps a changed file to a component.** An ``implemented_by`` entry
#   is a ``repo#path`` prefix: it speaks for a ``--repo`` whose own path ends
#   with the entry's repo half (``…/acme/orders`` for ``acme/orders``), and an
#   entry with no ``#`` names no repo and applies to every one — the
#   single-repo spelling. A file maps when it sits under such a prefix at a
#   path-segment boundary. Only full-fidelity components can map anything:
#   contract fidelity drops ``implemented_by``.
# - **Why out-of-scope is its own rule, not scope folded in.** An
#   ``out_of_scope`` component reaches the packet only by being named in the
#   milestone's own scope — full fidelity, ``implemented_by`` carried — so a
#   change under it maps and is this rule's finding. A ring neighbour sits at
#   contract fidelity, where ``implemented_by`` is dropped: a change under one
#   of those maps to nothing at all and is ``verify/scope``'s finding. The
#   contract cut is itself the fence; the two rules stay distinct.
# - **What covers an ``unknown``.** A decision the packet carries *and*
#   ``must_hold`` names, whose ``applies_to`` includes the component. Honest
#   assemblies keep the pair together — a decision applying to scope is
#   derived into ``must_hold`` and pulled in as a ring — so the conjunction
#   costs nothing real and stops a hand-narrowed packet laundering an unknown
#   with a decision it merely happens to carry.
# - **How deep "runs" goes.** ``verify/contract-tests`` checks that the named
#   file exists in a ``--repo`` and contains something test-shaped. Executing
#   the implementing repo's own test suite is a real design decision with
#   sandboxing and trust implications, one the spec defers: when it is made,
#   this rule's body is the one place the change lands.
# - **What a step definition is.** Pragmatically, a repo file that references
#   a criterion id — found by scanning the repos as text, skipping the
#   generated ``.feature`` files and the ``.absicht/`` store, both of which
#   name every criterion id without being step definitions. A search, not a
#   parse; the limitation is named where the heuristic is.

RULES.update(
    {
        "verify/scope": (
            "A changed file that maps to no component the packet carries at full "
            "fidelity: every path in each --repo's diff must sit under an in-scope "
            "component's implemented_by prefix, and an entry's repo half must name "
            "the --repo it speaks for. Always an error — scope leakage is the one "
            "question no generic quality gate can even ask."
        ),
        "verify/out-of-scope": (
            "A changed file mapping to a component whose packet-time state is "
            "out_of_scope: the design said do not build, the diff built anyway. "
            "Such a component is in the packet only through the milestone's own "
            "scope; a contract-fidelity neighbour cannot be mapped to at all, "
            "which makes that change verify/scope's finding instead. Always an "
            "error."
        ),
        "verify/unknown-basis": (
            "A changed file mapping to a component whose packet-time state is "
            "unknown, where no decision the packet carries and must_hold names "
            "applies to it — the README's 'ask, spike, or mark blocking; never "
            "invent', enforced after the fact. Always an error."
        ),
        "verify/contract-tests": (
            "A seam the packet carries at full fidelity whose verified_by is "
            "empty, names a file no --repo holds, or names a file containing "
            "nothing test-shaped. 'Runs' means exactly that existence-and-shape "
            "check for now; actually executing the implementing repo's test "
            "suite is a separately-decided follow-up, deliberately not smuggled "
            "in here."
        ),
        "verify/done-when": (
            "A criterion the packet carries that no file in any --repo "
            "references: nothing verifies it. A pragmatic text search for the "
            "criterion id, not a parse — it cannot tell a real check from a "
            "comment naming the id, and structural or measured criteria are only "
            "ever approximated by whatever source names them."
        ),
        "verify/scenarios-unmodified": (
            "The .feature files across the repos, hashed together, do not match "
            "packet.lock's scenarios_digest: a scenario was edited, added or "
            "deleted since the packet was sealed. This is literally what sealing "
            "exists for. Always an error."
        ),
        "verify/step-assertions": (
            "A file that references a criterion id — the working definition of a "
            "step definition — but contains nothing that looks like an "
            "assertion: a test that cannot fail. Warn, not error, and a "
            "heuristic by design: the assertion shapes it recognizes are "
            "deliberately simple, and an unfamiliar framework's spelling should "
            "nudge rather than fail CI; --strict promotes it."
        ),
    }
)

_KIND_PREFIX: dict[type[Element], str] = {
    Component: "component:",
    Seam: "seam:",
    Decision: "decision:",
}
"""The ref prefix each carried kind is read back through. A PacketElement's
``element`` is a model dump; validating it back through the model is the
type-safe read, rather than reaching into the dict and casting by hand."""


def _carried[E: Element](
    ctx: VerifyContext, model: type[E], *, fidelity: Fidelity | None = None
) -> tuple[E, ...]:
    """The packet's elements of one kind, re-read as that model, in packet order.

    ``fidelity`` narrows to one grade where a rule judges scope rather than
    presence; ``None`` reads every grade, and a contract-fidelity component
    simply validates with no ``implemented_by``, so it claims nothing."""
    prefix = _KIND_PREFIX[model]
    return tuple(
        model.model_validate(carried.element)
        for carried in ctx.packet.elements
        if carried.ref.startswith(prefix) and (fidelity is None or carried.fidelity is fidelity)
    )


def _claims(component: Component, repo: Path) -> tuple[Path, ...]:
    """The ``implemented_by`` path prefixes of ``component`` that speak for ``repo``.

    The repo half of an entry names a ``--repo`` by path suffix — the way a
    multi-repo slice names its units — and the repo is resolved first so a
    relative ``--repo`` (the default ``.``) matches on where it actually is."""
    resolved = repo.resolve()
    prefixes: list[Path] = []
    for entry in component.implemented_by:
        repo_half, sep, path = entry.partition("#")
        if not sep:
            # No "#": a bare path naming no repo, the single-repo spelling.
            repo_half, path = "", entry
        name = PurePosixPath(repo_half).parts
        if name and tuple(resolved.parts[-len(name) :]) != name:
            continue
        prefixes.append(Path(path))
    return tuple(prefixes)


def _under(prefix: Path, file: Path) -> bool:
    """Whether ``file`` sits under ``prefix`` at a path-segment boundary —
    ``src/core`` covers ``src/core/api.py`` and not ``src/corex/api.py``."""
    return prefix == file or prefix in file.parents


def _mapped(ctx: VerifyContext, component: Component) -> Iterator[tuple[Path, tuple[Path, ...]]]:
    """The repos where ``component``'s code changed, with the changed files that
    map to it — the one walk the three component rules judge differently."""
    for repo, changed in ctx.changed.items():
        prefixes = _claims(component, repo)
        hits = tuple(
            sorted(path for path in changed if any(_under(prefix, path) for prefix in prefixes))
        )
        if hits:
            yield repo, hits


def _unmapped(ctx: VerifyContext) -> Iterator[tuple[Path, Path]]:
    """Every changed file that maps to no component the packet puts in scope,
    as ``(repo, file)`` — the walk verify/scope reports, named as the mirror
    of ``_mapped``."""
    components = _carried(ctx, Component)
    for repo, changed in ctx.changed.items():
        claims = [prefix for component in components for prefix in _claims(component, repo)]
        for path in sorted(changed):
            if not any(_under(prefix, path) for prefix in claims):
                yield repo, path


def _scope_findings(ctx: VerifyContext) -> tuple[Finding, ...]:
    return tuple(
        finding(
            "verify/scope",
            severity=Severity.ERROR,
            message=f"{path.as_posix()} in {repo} maps to no component the packet puts in scope",
            source=path.as_posix(),
        )
        for repo, path in _unmapped(ctx)
    )


def _out_of_scope_findings(ctx: VerifyContext) -> tuple[Finding, ...]:
    """Every changed file that maps to a component the packet fences off."""
    findings: list[Finding] = []
    for component in _carried(ctx, Component):
        if component.state is not State.OUT_OF_SCOPE:
            continue
        for repo, hits in _mapped(ctx, component):
            names = ", ".join(path.as_posix() for path in hits)
            findings.append(
                finding(
                    "verify/out-of-scope",
                    severity=Severity.ERROR,
                    message=(
                        f"{component.id} is out_of_scope in the packet, "
                        f"but {names} in {repo} changed"
                    ),
                    ref=component.id,
                    source=component.source or None,
                )
            )
    return tuple(findings)


def _unknown_basis_findings(ctx: VerifyContext) -> tuple[Finding, ...]:
    """Every changed component that is ``unknown`` with no recorded answer."""
    must_hold = frozenset(ctx.packet.must_hold)
    covered = {
        applies
        for decision in _carried(ctx, Decision)
        if decision.id in must_hold
        for applies in decision.applies_to
    }
    findings: list[Finding] = []
    for component in _carried(ctx, Component):
        if component.state is not State.UNKNOWN or component.id in covered:
            continue
        for repo, hits in _mapped(ctx, component):
            names = ", ".join(path.as_posix() for path in hits)
            findings.append(
                finding(
                    "verify/unknown-basis",
                    severity=Severity.ERROR,
                    message=(
                        f"{component.id} is unknown in the packet and no decision "
                        f"that must hold covers it, but {names} in {repo} changed"
                    ),
                    ref=component.id,
                    source=component.source or None,
                )
            )
    return tuple(findings)


_TEST_SHAPES: tuple[str, ...] = (
    "def test",  # Python, any runner
    "func test",  # Go
    "@test",  # JUnit, PHPUnit
    "it('",
    'it("',
    "test('",
    'test("',  # the JS family
)
"""What ``contains something that looks like a test`` matches: deliberately
simple substrings, compared case-insensitively. A heuristic, not a parser —
the explain text for the rule that uses it says so too."""

_ASSERTION_SHAPES: tuple[str, ...] = ("assert", "expect(")
"""The same bargain one rule over: generous substrings, case-insensitive,
named a heuristic wherever they decide a finding."""


def _looks_like_a_test(text: str) -> bool:
    folded = text.casefold()
    return any(shape in folded for shape in _TEST_SHAPES)


def _asserts(text: str) -> bool:
    folded = text.casefold()
    return any(shape in folded for shape in _ASSERTION_SHAPES)


def _contract_tests_findings(ctx: VerifyContext) -> tuple[Finding, ...]:
    """Every in-scope seam whose named contract tests are missing or hollow."""
    findings: list[Finding] = []
    for seam in _carried(ctx, Seam, fidelity=Fidelity.FULL):
        problems = ["verified_by names nothing"] if not seam.verified_by else []
        for named in seam.verified_by:
            # A "::" suffix narrows to one test inside a file — pytest's id
            # spelling — and existence is a property of the file.
            path = named.split("::", 1)[0]
            found = next((repo / path for repo in ctx.repos if (repo / path).is_file()), None)
            if found is None:
                problems.append(f"{named} is no file in any --repo")
            elif not _looks_like_a_test(found.read_text(encoding="utf-8", errors="replace")):
                problems.append(f"{named} contains nothing that looks like a test")
        if problems:
            findings.append(
                finding(
                    "verify/contract-tests",
                    severity=Severity.ERROR,
                    message=f"{seam.id}: {'; '.join(problems)}",
                    ref=seam.id,
                    source=seam.source or None,
                )
            )
    return tuple(findings)


def _step_sources(ctx: VerifyContext) -> dict[tuple[Path, Path], frozenset[str]]:
    """Every repo file that references at least one criterion id, as
    ``(repo, repo-relative file) -> the ids it references`` — the working
    definition of a step definition, shared by the two criteria rules.

    The generated ``.feature`` files are skipped: a scenario names its own
    criterion in the ``Scenario:`` header, and counting that would make
    done-when vacuously pass. So is ``.absicht/``, which holds the packet body
    itself — every criterion id in it — when design and code share a repo. A
    file verify cannot read is skipped rather than fatal: unreadable does not
    make it a step definition."""
    needles = tuple((criterion.id, criterion.id.encode()) for criterion in ctx.packet.criteria)
    sources: dict[tuple[Path, Path], frozenset[str]] = {}
    for repo in ctx.repos:
        for path in sorted(repo.glob("**/*")):
            if not _scannable(path):
                continue
            try:
                content = path.read_bytes()
            except OSError:
                continue
            hits = frozenset(text for text, needle in needles if needle in content)
            if hits:
                sources[(repo, path.relative_to(repo))] = hits
    return sources


def _scannable(path: Path) -> bool:
    """A file the step scan reads: not a directory, not git's own tree, not a
    generated scenario, not the store."""
    return (
        path.is_file()
        and ".git" not in path.parts
        and ".absicht" not in path.parts
        and path.suffix != ".feature"
    )


def _done_when_findings(ctx: VerifyContext) -> tuple[Finding, ...]:
    """Every criterion the packet carries that nothing in the repos references."""
    referenced = {criterion_id for hits in _step_sources(ctx).values() for criterion_id in hits}
    return tuple(
        finding(
            "verify/done-when",
            severity=Severity.ERROR,
            message=(
                f"nothing in the repos references {criterion.id}: "
                "no step definition or check verifies it"
            ),
            ref=criterion.id.split("#", 1)[0],
        )
        for criterion in ctx.packet.criteria
        if criterion.id not in referenced
    )


def _scenarios_unmodified_findings(ctx: VerifyContext) -> tuple[Finding, ...]:
    """The sealed scenarios, re-hashed from the repos as they stand now."""
    found = _feature_files(ctx)
    digest = scenario_digest(found)
    if digest == ctx.lock.scenarios_digest:
        return ()
    names = ", ".join(sorted(found)) or "no .feature files at all"
    return (
        finding(
            "verify/scenarios-unmodified",
            severity=Severity.ERROR,
            message=(
                f"the .feature files in the repos hash to {digest}, "
                f"not the sealed {ctx.lock.scenarios_digest} (found: {names})"
            ),
        ),
    )


def _feature_files(ctx: VerifyContext) -> dict[str, str]:
    """The ``.feature`` files across the repos, keyed by file name — the shape
    the sealed digest hashes. Undecodable bytes become U+FFFD, so a corrupted
    file is a digest mismatch rather than a crash. Git's own tree holds no
    ``.feature`` files, so the walk needs no ``.git`` skip the way the step
    scan does."""
    features: dict[str, str] = {}
    for repo in ctx.repos:
        for path in sorted(repo.glob("**/*.feature")):
            features[path.name] = path.read_bytes().decode("utf-8", errors="replace")
    return features


def _step_assertions_findings(ctx: VerifyContext) -> tuple[Finding, ...]:
    """Every step definition that cannot fail."""
    findings: list[Finding] = []
    for repo, path in _step_sources(ctx):
        if not _asserts((repo / path).read_text(encoding="utf-8", errors="replace")):
            findings.append(
                finding(
                    "verify/step-assertions",
                    severity=Severity.WARN,
                    message=(
                        f"{path.as_posix()} references criterion ids but nothing "
                        "that looks like an assertion"
                    ),
                    source=path.as_posix(),
                )
            )
    return tuple(findings)


VERIFY_RULES.update(
    {
        "verify/scope": _scope_findings,
        "verify/out-of-scope": _out_of_scope_findings,
        "verify/unknown-basis": _unknown_basis_findings,
        "verify/contract-tests": _contract_tests_findings,
        "verify/done-when": _done_when_findings,
        "verify/scenarios-unmodified": _scenarios_unmodified_findings,
        "verify/step-assertions": _step_assertions_findings,
    }
)
