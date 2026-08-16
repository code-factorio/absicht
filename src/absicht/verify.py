"""``ab verify``'s scaffolding: the sealed packet, the diff, the rules' running.

``CONTEXT.md`` calls ``ab verify`` *"the entire premise of the project"* — the
one check that asks whether the code is the code that was asked for, not just
whether it is well-formed. This module is the frame around that question; the
rules themselves are ``docs/tasks/41-verify-rules.md``'s, and they hang off
``VERIFY_RULES`` and ``VerifyContext`` exactly as built here.

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

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from absicht.findings import Finding, Report
from absicht.git import GitError, changed_paths
from absicht.models import Packet, PacketLock


class VerifyUsageError(Exception):
    """A broken invocation. The CLI maps this to ``ExitCode.USAGE``."""


type VerifyRule = Callable[[VerifyContext], tuple[Finding, ...]]
"""One rule: everything it may look at is the context, what it says back is
findings — the shape ``absicht.check``'s layers have, against a different
input."""


VERIFY_RULES: dict[str, VerifyRule] = {}
"""The rules ``ab verify`` runs, by id, in registration order.

A plain dict, like ``absicht.findings.RULES``: a handful of rules is a lookup,
not a plugin system. Empty until ``docs/tasks/41-verify-rules.md`` lands the
rule bodies; each rule's ``--explain`` text registers in ``findings.RULES``
like every other rule-producing module's."""


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
