"""``ab status``: where the code stands against the design.

A read-only report, like every other query in this project, computed from the
two halves the README's Discovery section joins: the design store (what is
true) and the repos' `.absicht` markers (how much of it has landed). Which
half matters depends on the mode `locate_store` already determined:

- **Reference mode** — the store was reached through a marker, design and code
  live apart, and a watermark is the join. Each unit's watermark is compared
  against design head (or ``--since``): the decision and seam changes that
  landed in between and touch it are its drift, and a seam whose provider's
  watermark covers a change a consumer's does not is a consumer silently
  running an old contract. The walk is a git diff of the design store itself
  between the two revs — "which decisions and seam changes landed since the
  watermark" is a question about history, not about two structural snapshots,
  which is why this does not borrow `absicht.diff`'s element-by-element
  comparison.
- **Embedded mode** — the store was reached as a directory, design and code
  land in the same commit and nothing can be behind. What is left is
  implementation coverage: components with no `implemented_by`, and
  milestones whose `done_when` criteria nothing claims to verify.

Both modes report the coverage half; the watermark half exists only in
reference mode, where ``--repo`` is effectively required — `System.units`
names repos by suffix, which cannot locate them on disk.

Two judgement calls worth naming out loud:

- **A watermark is a hint, not proof.** It tends to over-claim (a merge stamps
  it whether or not the work was finished), and so does everything computed
  from it: this module reports drift, never verifies landing. The same
  humility shapes the `done_when` check, which is the weaker half of `ab
  verify`'s done-when rule — "does anything claim to verify this criterion"
  (a file in the repos referencing its id), never "did verification actually
  pass". A sealed packet and `ab verify` are what answer the stronger
  question.
- **Attribution is direct.** A decision change touches a unit when the
  decision's `applies_to` names it; a seam change when the unit provides or
  consumes the seam. No subtree descent, and no cross-check against the
  design: a watermark whose component the design no longer carries finds
  nothing touching it, which is `ab marker check`'s finding to report, not
  drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from absicht.git import GitError, changed_between, current_rev, repo_root, resolve_rev
from absicht.load import LocatedStore, StoreMode
from absicht.markers import read as read_marker
from absicht.models.design import FORMAT_VERSION, Design, Ref, RelationshipType
from absicht.models.marker import Watermark
from absicht.resolve import Index


class StatusUsageError(Exception):
    """A broken invocation. The CLI maps this to ``ExitCode.USAGE``."""


_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
"""The empty tree's well-known sha: the base for a watermark that was never
stamped. A marker fresh from `ab marker sync` records that nothing has landed,
so everything the design has ever committed is unlanded work — spelled as a
revision git can diff against, rather than an error or a special case."""


@dataclass(frozen=True, slots=True)
class UnitReport:
    """One watermark, judged: what landed in the design since it."""

    repo: Path
    watermark: Watermark
    decisions: tuple[Ref, ...]
    interfaces: tuple[Ref, ...]

    @property
    def behind(self) -> bool:
        return bool(self.decisions or self.interfaces)


@dataclass(frozen=True, slots=True)
class ConsumerLag:
    """An interface whose contract moved past a caller's watermark while the
    declaring side's own watermark covers the change — the asymmetric case
    worth naming beyond the per-unit lists, where both sides being behind
    would make the interface just one line among that unit's drift."""

    interface: Ref
    consumer: Ref
    repo: Path
    provider: Ref


@dataclass(frozen=True, slots=True)
class UnmetObservation:
    """A `done_when` observation nothing claims to verify."""

    milestone: Ref
    observation: str


@dataclass(frozen=True, slots=True)
class StatusReport:
    """The whole answer, in the mode's own vocabulary: watermark drift in
    reference mode, coverage in both."""

    mode: StoreMode
    against: str | None
    """The design rev watermarks were judged against — head, or `--since`."""

    units: tuple[UnitReport, ...]
    consumers_behind: tuple[ConsumerLag, ...]
    no_implementation: tuple[Ref, ...]
    done_when_unmet: tuple[UnmetObservation, ...]

    @property
    def drift(self) -> bool:
        """Whether any unit is behind or any consumer has not caught up —
        what ``--fail-on-drift`` turns into an exit code. Coverage gaps are
        not drift: an unimplemented component or an unmet observation is the
        design's own unfinished business, not the code falling behind it."""
        return any(unit.behind for unit in self.units) or bool(self.consumers_behind)

    def render_text(self) -> str:
        """One line per fact, grep-friendly like every other report here; an
        empty report is the empty string (silence is the nothing-to-do
        signal). The `done_when` line says *claims* on purpose: a claim is not
        a pass, and the wording is where that distinction lives."""
        lines = [
            *(
                f"current: {unit.watermark.id} in {unit.repo}"
                for unit in self.units
                if not unit.behind
            ),
            *(
                f"behind: {unit.watermark.id} in {unit.repo}: "
                f"{', '.join([*unit.decisions, *unit.interfaces])} {_since(unit.watermark)}"
                for unit in self.units
                if unit.behind
            ),
            *(
                f"consumer behind: {lag.interface}: {lag.consumer} in {lag.repo} has not "
                f"caught up; provider {lag.provider} is current"
                for lag in self.consumers_behind
            ),
            *(f"no implementation: {ref}" for ref in self.no_implementation),
            *(
                f"done_when unmet: {unmet.milestone} {unmet.observation}: "
                "nothing claims to verify it"
                for unmet in self.done_when_unmet
            ),
        ]
        return "\n".join(lines)

    def render_json(self) -> dict[str, object]:
        """The ``--format json`` envelope from docs/tasks/00-conventions.md."""
        return {
            "format_version": FORMAT_VERSION,
            "mode": self.mode.value,
            "against": self.against,
            "units": [
                {
                    "repo": str(unit.repo),
                    "id": unit.watermark.id,
                    "path": unit.watermark.path,
                    "at": unit.watermark.at,
                    "design_rev": unit.watermark.design_rev,
                    "decisions": list(unit.decisions),
                    "interfaces": list(unit.interfaces),
                }
                for unit in self.units
            ],
            "consumers_behind": [
                {
                    "interface": lag.interface,
                    "consumer": lag.consumer,
                    "repo": str(lag.repo),
                    "provider": lag.provider,
                }
                for lag in self.consumers_behind
            ],
            "no_implementation": list(self.no_implementation),
            "done_when_unmet": [
                {"milestone": unmet.milestone, "observation": unmet.observation}
                for unmet in self.done_when_unmet
            ],
        }


def _since(watermark: Watermark) -> str:
    """The tail of a behind line: which rev the unit landed at, or that it
    never did."""
    if watermark.design_rev is None:
        return "(never stamped)"
    return f"since {watermark.design_rev[:7]}"


def status(
    design: Design,
    location: LocatedStore,
    *,
    repos: tuple[Path, ...] = (),
    unit: str | None = None,
    since: str | None = None,
    behind_only: bool = False,
) -> StatusReport:
    """Judge the code against the design, per the mode `location` names.

    `MarkerError` (a repo with no readable marker) and `GitError` (a design
    store outside any repository, a rev that does not resolve) pass through
    for the CLI to map to ``USAGE``; `StatusUsageError` covers the invocations
    only this command can see coming — reference mode without ``--repo``, an
    unknown ``--unit``.
    """
    if location.mode is StoreMode.EMBEDDED:
        return _embedded(design, location)
    return _reference(
        design, location, repos=repos, unit=unit, since=since, behind_only=behind_only
    )


def _embedded(design: Design, location: LocatedStore) -> StatusReport:
    """The embedded report: coverage only, nothing to be behind.

    The store's own repository is where claims are looked for — that is what
    design and code sharing a repo means. A store outside any repository has
    nowhere to look, so nothing claims anything and every `done_when`
    observation reports unmet: honest, and no crash over a store git has never
    seen."""
    try:
        roots: tuple[Path, ...] = (repo_root(location.root),)
    except GitError:
        roots = ()
    return StatusReport(
        mode=StoreMode.EMBEDDED,
        against=None,
        units=(),
        consumers_behind=(),
        no_implementation=_no_implementation(design),
        done_when_unmet=_unmet(design, roots, skip=location.root),
    )


def _reference(
    design: Design,
    location: LocatedStore,
    *,
    repos: tuple[Path, ...],
    unit: str | None,
    since: str | None,
    behind_only: bool,
) -> StatusReport:
    """The reference report: every named repo's watermarks against one rev."""
    if not repos:
        raise StatusUsageError(
            "reference mode: pass --repo PATH for every implementing repo — "
            "a marker names repos by suffix, which cannot locate them on disk"
        )
    against = resolve_rev(since, location.root) if since is not None else current_rev(location.root)
    # dict.fromkeys keeps the first spelling of a repeated --repo, the same
    # dedupe `absicht.verify.context_for` makes: one diff per repo, not one
    # per spelling of it.
    resolved = tuple(dict.fromkeys(repos))
    watermarks = [(repo, watermark) for repo in resolved for watermark in read_marker(repo).units]
    if unit is not None and not any(watermark.id == unit for _, watermark in watermarks):
        raise StatusUsageError(
            f"--unit {unit}: no watermark in any --repo's marker carries that unit"
        )
    # Every watermark is judged, even under --unit: the consumer-lag half
    # needs the provider's watermark to say "the provider is current", so the
    # filter restricts what is reported below, never what is gathered here.
    judged = [
        (repo, watermark, _refs_since(location.root, watermark, against))
        for repo, watermark in watermarks
    ]
    index = Index(design)
    units = tuple(
        _unit_report(design, index, repo, watermark, changed) for repo, watermark, changed in judged
    )
    if unit is not None:
        units = tuple(unit_report for unit_report in units if unit_report.watermark.id == unit)
    if behind_only:
        units = tuple(unit_report for unit_report in units if unit_report.behind)
    consumers_behind = _consumer_lag(design, index, judged)
    if unit is not None:
        consumers_behind = tuple(lag for lag in consumers_behind if lag.consumer == unit)
    return StatusReport(
        mode=StoreMode.REFERENCE,
        against=against,
        units=units,
        consumers_behind=consumers_behind,
        no_implementation=_no_implementation(design),
        # Claims live where the code lives: the implementing repos, never the
        # design store (its behaviors name their own observations).
        done_when_unmet=_unmet(design, resolved, skip=None),
    )


def _no_implementation(design: Design) -> tuple[Ref, ...]:
    """The coverage half both modes report: components with no implementation
    reference, in the design's own order."""
    return tuple(component.id for component in design.components if not component.implemented_by)


def _refs_since(root: Path, watermark: Watermark, against: str) -> frozenset[Ref]:
    """The decision and interface refs the design store changed between the
    watermark's rev and `against`.

    The diff runs in the design store's own repository, restricted to the
    store's kind directories (a store may sit in a subdirectory of the repo,
    so the paths are joined onto the store's repo-relative prefix — the same
    join `absicht.build` makes for `--rev`). Only the two kinds a unit can be
    behind on are walked: what was decided, and what it has to talk through. A
    changed file whose slug names nothing in the design — renamed or deleted
    since — cannot be attributed and is dropped rather than reported as a ref
    nobody can act on.
    """
    base = watermark.design_rev if watermark.design_rev is not None else _EMPTY_TREE
    repo = repo_root(root)
    prefix = root.resolve().relative_to(repo.resolve())
    changed = changed_between(
        base, against, repo, paths=(prefix / "decisions", prefix / "interfaces")
    )
    kinds = {"decisions": "decision", "interfaces": "interface"}
    return frozenset(
        f"{kinds[path.parts[-2]]}:{path.stem}"
        for path in changed
        if path.suffix == ".md" and len(path.parts) >= 2 and path.parts[-2] in kinds
    )


def _unit_report(
    design: Design, index: Index, repo: Path, watermark: Watermark, changed: frozenset[Ref]
) -> UnitReport:
    """The watermark's drift: which changed decisions apply to it and which
    changed interfaces it declares or calls, in the design's own order."""
    called = {
        target for source, target in index.edges(RelationshipType.CALLS) if source == watermark.id
    }
    return UnitReport(
        repo=repo,
        watermark=watermark,
        decisions=tuple(
            decision.id
            for decision in design.decisions
            if decision.id in changed and watermark.id in decision.applies_to
        ),
        interfaces=tuple(
            interface.id
            for interface in design.interfaces
            if interface.id in changed
            and (interface.declared_by == watermark.id or interface.id in called)
        ),
    )


def _consumer_lag(
    design: Design,
    index: Index,
    judged: list[tuple[Path, Watermark, frozenset[Ref]]],
) -> tuple[ConsumerLag, ...]:
    """Interfaces whose callers have not caught up while the declaring side has.

    An interface is lagged when it changed since a calling unit's watermark
    but not since the declaring one's — the declaring side has landed the new
    contract, the caller is still running the old one. Both behind is ordinary
    drift (the per-unit lists say it); a declaring side with no watermark at
    all cannot be said to have moved past anything, so its interfaces are not
    lagged here. The first watermark seen per component speaks for it: a
    component implemented across repos is one unit with one contract."""
    by_component: dict[Ref, tuple[Path, frozenset[Ref]]] = {}
    for repo, watermark, changed in judged:
        by_component.setdefault(watermark.id, (repo, changed))
    callers: dict[Ref, list[Ref]] = {}
    for source, target in index.edges(RelationshipType.CALLS):
        callers.setdefault(target, []).append(source)
    lags: list[ConsumerLag] = []
    for interface in design.interfaces:
        if interface.declared_by is None:
            continue
        provider = by_component.get(interface.declared_by)
        if provider is None or interface.id in provider[1]:
            continue
        lags.extend(
            ConsumerLag(
                interface=interface.id,
                consumer=consumer,
                repo=entry[0],
                provider=interface.declared_by,
            )
            for consumer in callers.get(interface.id, ())
            if (entry := by_component.get(consumer)) is not None and interface.id in entry[1]
        )
    return tuple(lags)


def _unmet(
    design: Design, roots: tuple[Path, ...], *, skip: Path | None
) -> tuple[UnmetObservation, ...]:
    """Every `done_when` observation nothing claims to verify, milestone by
    milestone."""
    wanted = [
        (milestone.id, observation)
        for milestone in design.milestones
        for observation in milestone.done_when
    ]
    claimed = _claimed_ids(roots, tuple(observation for _, observation in wanted), skip=skip)
    return tuple(
        UnmetObservation(milestone=milestone, observation=observation)
        for milestone, observation in wanted
        if observation not in claimed
    )


def _claimed_ids(
    roots: tuple[Path, ...], observations: tuple[str, ...], *, skip: Path | None
) -> frozenset[str]:
    """Which observations some file in `roots` references — the working
    definition of a claim, searched as bytes so a binary or oddly-encoded
    file is a non-match rather than a crash."""
    # `skip` arrives as the caller spelled the store — `.absicht` by default —
    # while the walk's paths share `repo_root`'s absolute spelling. Resolved
    # once here, the two spellings compare; left alone, `is_relative_to` would
    # be False for every file and the store would claim its own observations.
    resolved_skip = skip.resolve() if skip is not None else None
    needles = tuple((observation, observation.encode()) for observation in observations)
    claimed: set[str] = set()
    for root in roots:
        for path in sorted(root.glob("**/*")):
            if not _scannable(path, resolved_skip):
                continue
            try:
                content = path.read_bytes()
            except OSError:
                # Unreadable does not make a file a claim.
                continue
            claimed.update(text for text, needle in needles if needle in content)
    return frozenset(claimed)


def _scannable(path: Path, skip: Path | None) -> bool:
    """A file the claim scan reads: not a directory, not git's own tree, not
    a generated scenario (a `.feature` header names its observation), and not
    the store — the same exclusions `ab verify`'s step scan makes, with the
    store skipped by where it actually is rather than by name, since
    `--store` need not spell it `.absicht`."""
    return (
        path.is_file()
        and ".git" not in path.parts
        and path.suffix != ".feature"
        and (skip is None or not path.is_relative_to(skip))
    )
