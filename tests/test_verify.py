"""``ab verify``: the scaffolding, then the seven rules that hang in it.

``docs/tasks/40-verify-core.md`` builds the frame that
``docs/tasks/41-verify-rules.md`` fills in, so what these tests pin is the
frame first —

- ``load_sealed_packet`` reads back exactly what ``ab packet --seal`` wrote —
  offline, no design store — and refuses what it cannot read back (a missing
  lock, a Markdown-only body) as a usage error naming the fix;
- the default ``--packet`` discovery refuses to guess: zero or two sealed
  packets under the build dir is a usage error, exactly one is used;
- ``context_for`` resolves one diff per ``--repo`` against ``--diff-base`` —
  the multi-repo shape the rules will read;
- ``--rule``/``--exclude-rule`` select which rules run (against fake rules
  registered for the test, so the selection stays pinned independently of
  what the real rule set happens to find over the clean store), an unknown
  id is a usage error, and ``--strict`` promotes the warnings that survive;
- ``--report`` writes the rendered report *in addition to* stdout, and an
  empty report stays silent on stdout while still writing the (empty) file.

Then 41's seven rules, each as the pair ``verification.md`` asks of every
rule: a sealed packet and a repo diff that trip it, and the same shape not
tripping it — plus one end-to-end run against a packet sealed for real from
``clean/``, over a repo built to satisfy all seven at once.

``docs/tasks/59-verify-observations.md`` adds the eighth, over the packet's
behaviors rather than its diff: every ``must``/``must_not`` observation of the
satisfy and must-not-break sets has something referencing it. The three
outcomes the addendum's §9 table names are pinned per observation —
``checked`` with evidence, ``no_check`` as the finding, ``advisory`` for a
``should``, reported in the summary and never in the exit code — and every
observation lands in the run store. A ``done_when`` entry is an observation id
now, so it rides in that same walk rather than a criterion row of its own.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from absicht import runstore, verify
from absicht.cli import app
from absicht.cli._common import DEFAULT_PACKET_DIR, STORE_ENVVAR, ExitCode
from absicht.findings import RULES, Finding, Severity, finding
from absicht.gherkin import observations_digest
from absicht.git import current_rev
from absicht.models.design import (
    FORMAT_VERSION,
    Behavior,
    Component,
    ComponentLevel,
    Decision,
    Element,
    Interface,
    InterfaceStyle,
    Observation,
    Outcome,
    Resource,
    ResourceKind,
    State,
    Timing,
)
from absicht.models.packet import Fidelity, Packet, PacketElement, PacketLock
from absicht.runstore import RunResult

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"

# Hand-built stand-ins for a sealed pair: the plumbing under test needs the
# models' shapes, not a real seal.
_PACKET = Packet(milestone="milestone:m1", design="design:acme")
_LOCK = PacketLock(design_rev="0" * 40, observations_digest="deadbeef")

# `clean/`'s one in-scope behavior carries a `should` observation, so every run
# over the sealed clean packet ends with the advisory summary — and the store
# itself, handed to --repo as a stand-in, names every observation id in its own
# behavior file, which is what checks that `should`.
_CLEAN_ADVISORY = [
    "advisory behavior:order-cancelled#obs-3 (should, eventual): "
    "checked by behaviors/order-cancelled.md"
]


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """Fixture plumbing: run git in ``repo``, failing loudly if git does."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **env} if env else None,
    ).stdout


# A fixed instant for every `c1`: same content plus same stamp is the same
# commit sha. test_the_resolved_diff_is_per_repo hands one repo's `HEAD~1` to
# another repo as `--diff-base`, which only resolves when the two one-commit
# repos share their sha — a property of the fixtures, never of the clock
# (two commits landing in different seconds made CI's run fail with "Invalid
# symmetric difference expression").
_PINNED_COMMIT_DATES = {
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}


def _init_repo(repo: Path) -> None:
    """Turn an existing directory into a one-commit git repository."""
    _git(repo, "init", "-q", "-b", "main")
    # A bare CI machine has no git identity, and commits must not try to sign.
    _git(repo, "config", "user.email", "tests@absicht.invalid")
    _git(repo, "config", "user.name", "absicht tests")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c1", env=_PINNED_COMMIT_DATES)


def _repo(tmp_path: Path, name: str, files: dict[str, str]) -> Path:
    """A one-commit git repository holding ``files`` — an implementing repo.
    ``name`` may nest (`acme/core`): an implemented_by repo half names a path,
    so the repo that matches it has to be buildable at one."""
    repo = tmp_path / name
    repo.mkdir(parents=True)
    for path, content in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _init_repo(repo)
    return repo


def _seal(tmp_path: Path, *flags: str, out: Path | None = None) -> tuple[Path, Path]:
    """A packet sealed the only way one ever is: by the real ``ab packet
    --seal``, from the ``clean/`` fixture made a one-commit repo (a seal needs
    a rev to stamp). ``out=None`` exercises the default build dir, which is
    cwd-relative."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    _init_repo(store)
    argv = ["--store", str(store), "packet", "milestone:m1", "--seal", *flags]
    if out is not None:
        argv += ["--out", str(out)]
    built = runner.invoke(app, argv)
    assert built.exit_code == ExitCode.OK
    return store, out if out is not None else DEFAULT_PACKET_DIR / "m1"


@pytest.fixture(autouse=True)
def _ambient_store(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Where a run with no ``--store`` records: a directory the test session
    owns, never the repository absicht is run from. Verification is offline and
    reaches for a store only to leave history, so an unnamed one must not be
    the developer's own — a test that wrote there would be reading a machine
    instead of a fixture."""
    monkeypatch.setenv(STORE_ENVVAR, str(tmp_path_factory.mktemp("ambient")))


@pytest.fixture
def sealed(tmp_path: Path) -> tuple[Path, Path]:
    """A machine-readable sealed packet plus the repo it was sealed from: the
    store for the seal, a stand-in ``--repo`` for the diff."""
    store, out = _seal(tmp_path, "--format", "json", out=tmp_path / "packet")
    return store, out / "packet.lock"


@contextmanager
def _cwd(directory: Path) -> Iterator[Path]:
    """Run with the cwd moved into a directory the test owns, so a relative
    default discovery (``.absicht/build/packets``) lands there — typer's
    CliRunner has no isolated filesystem of its own."""
    directory.mkdir(parents=True, exist_ok=True)
    origin = Path.cwd()
    os.chdir(directory)
    try:
        yield directory
    finally:
        os.chdir(origin)


@pytest.fixture
def fake_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two rules registered for the test. One fires an error, the other a
    warning, so filtering and ``--strict`` each have something to move; the
    explain catalog gets entries too, because ``finding()`` pulls from it."""

    def fire(rule_id: str, severity: Severity, message: str) -> verify.VerifyRule:
        def rule(_: verify.VerifyContext) -> tuple[Finding, ...]:
            return (finding(rule_id, severity=severity, message=message),)

        return rule

    monkeypatch.setattr(
        verify,
        "VERIFY_RULES",
        {
            "fake/one": fire("fake/one", Severity.ERROR, "one fired"),
            "fake/two": fire("fake/two", Severity.WARN, "two fired"),
        },
    )
    for rule_id in ("fake/one", "fake/two"):
        monkeypatch.setitem(RULES, rule_id, "a rule registered for the test")


def _verify(lock: Path, repo: Path, *flags: str) -> Result:
    """``ab verify`` against a sealed packet, in a repo whose HEAD diff is
    empty — the flags name whatever the test varies."""
    return runner.invoke(
        app, ["verify", "--packet", str(lock), "--repo", str(repo), "--diff-base", "HEAD", *flags]
    )


# ---------------------------------------------------------------------- loading


def test_load_sealed_packet_round_trips_a_cli_sealed_packet(sealed: tuple[Path, Path]) -> None:
    repo, lock_path = sealed

    packet, lock = verify.load_sealed_packet(lock_path)

    body = lock_path.parent / "packet.json"
    assert packet == Packet.model_validate_json(body.read_text(encoding="utf-8"))
    assert packet.milestone == "milestone:m1"
    # The digest is not a packet field: it is over the .feature files sealed
    # beside it, so re-hashing those is what a round trip has to agree with.
    rendered = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((lock_path.parent / "features").iterdir())
    }
    assert lock == PacketLock(
        format_version=FORMAT_VERSION,
        design_rev=current_rev(repo),
        observations_digest=observations_digest(rendered),
    )


def test_a_missing_lock_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(verify.VerifyUsageError, match="no sealed packet"):
        verify.load_sealed_packet(tmp_path / "packet.lock")


def test_an_md_sealed_packet_cannot_be_read_back(tmp_path: Path) -> None:
    """The default ``--format md`` body is for humans; verify needs the model,
    so an md-only seal is a usage error naming the fix, not a parse attempt."""
    _, out = _seal(tmp_path)

    with pytest.raises(verify.VerifyUsageError, match="--format json"):
        verify.load_sealed_packet(out / "packet.lock")


# ------------------------------------------------------------------- discovery


def _candidate(packets: Path, milestone: str) -> Path:
    lock = packets / milestone / "packet.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch()
    return lock


def test_discovery_finds_the_one_sealed_packet(tmp_path: Path) -> None:
    packets = tmp_path / "packets"
    only = _candidate(packets, "m1")

    assert verify.discover_sealed_packet(packets) == only


def test_discovery_with_no_sealed_packet_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(verify.VerifyUsageError, match="--packet"):
        verify.discover_sealed_packet(tmp_path / "packets")


def test_discovery_with_two_sealed_packets_refuses_to_guess(tmp_path: Path) -> None:
    packets = tmp_path / "packets"
    _candidate(packets, "m1")
    _candidate(packets, "m2")

    with pytest.raises(verify.VerifyUsageError, match="m2"):
        verify.discover_sealed_packet(packets)


# ------------------------------------------------------------------- the diff


def test_the_resolved_diff_is_per_repo(tmp_path: Path) -> None:
    quiet = _repo(tmp_path, "quiet", {"app.py": "one\n"})
    busy = _repo(tmp_path, "busy", {"app.py": "one\n"})
    (busy / "app.py").write_text("two\n", encoding="utf-8")
    (busy / "new.py").write_text("print('later')\n", encoding="utf-8")
    _git(busy, "add", "-A")
    _git(busy, "commit", "-qm", "c2")
    base = _git(busy, "rev-parse", "HEAD~1").strip()

    context = verify.context_for(_PACKET, _LOCK, diff_base=base, repos=(quiet, busy))

    assert context.repos == (quiet, busy)
    assert context.diff_base == base
    # Paths relative to each repo's own root — the shape rules match against.
    assert context.changed == {
        quiet: frozenset(),
        busy: frozenset({Path("app.py"), Path("new.py")}),
    }


def test_a_repo_that_is_not_a_directory_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(verify.VerifyUsageError, match="--repo"):
        verify.context_for(_PACKET, _LOCK, diff_base="HEAD", repos=(tmp_path / "nope",))


def test_a_diff_base_that_does_not_resolve_is_a_usage_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "code", {"app.py": "one\n"})

    with pytest.raises(verify.VerifyUsageError, match="no-such-ref"):
        verify.context_for(_PACKET, _LOCK, diff_base="no-such-ref", repos=(repo,))


# ----------------------------------------------------------------- the command


def test_an_empty_report_is_an_empty_pass(tmp_path: Path) -> None:
    """A run with nothing to say still has to answer OK, stay silent on stdout
    in text — the pass signal a human greps for — and honour --report even for
    an empty rendering. One rule selected, one that has nothing to say over the
    empty diff: the rules are real now, so the emptiness has to be earned."""
    repo = _repo(tmp_path, "code", {"app.py": "one\n"})
    lock = _seal_pair(
        tmp_path, Packet(milestone="milestone:m", design="design:acme"), scenarios=None
    )
    written = tmp_path / "reported.txt"

    plain = _verify(lock, repo, "--rule", "verify/scope", "--report", str(written))
    as_json = _verify(lock, repo, "--rule", "verify/scope", "--format", "json")

    assert plain.exit_code == ExitCode.OK
    assert plain.stdout == ""
    assert written.read_text(encoding="utf-8") == ""
    # The observation summary rides in every verify envelope, empty or not:
    # an additive field, so the machine shape is stable run to run.
    assert json.loads(as_json.stdout) == {
        "format_version": FORMAT_VERSION,
        "findings": [],
        "summary": {"unchecked_should": 0, "advisories": []},
    }


def test_rule_and_exclude_rule_select_which_rules_run(
    sealed: tuple[Path, Path], fake_rules: None
) -> None:
    repo, lock = sealed

    both = _verify(lock, repo)
    only_warn = _verify(lock, repo, "--rule", "fake/two")
    without_error = _verify(lock, repo, "--exclude-rule", "fake/one")
    strict = _verify(lock, repo, "--rule", "fake/two", "--strict")

    assert both.exit_code == ExitCode.FINDINGS  # fake/one is an error
    assert "error fake/one: one fired" in both.stdout
    assert "warn fake/two: two fired" in both.stdout
    # A warning alone passes; --strict is what promotes it. The advisory
    # summary is not a rule's output, so no --rule selection can suppress it.
    assert only_warn.exit_code == ExitCode.OK
    assert only_warn.stdout.splitlines() == ["warn fake/two: two fired", *_CLEAN_ADVISORY]
    assert without_error.exit_code == ExitCode.OK
    assert "fake/one" not in without_error.stdout
    assert "fake/two" in without_error.stdout
    assert strict.exit_code == ExitCode.FINDINGS


def test_an_unknown_rule_id_is_a_usage_error(sealed: tuple[Path, Path], fake_rules: None) -> None:
    """A typo'd id silently running nothing would exit 0 in CI — the one place
    verify is built to run — so it is refused, naming the rules that exist."""
    repo, lock = sealed

    result = _verify(lock, repo, "--rule", "verify/nope")

    assert result.exit_code == ExitCode.USAGE
    assert "verify/nope" in result.stderr
    assert "fake/one" in result.stderr
    assert result.stdout == ""


def test_report_writes_the_file_and_stdout_still_renders(
    sealed: tuple[Path, Path], fake_rules: None, tmp_path: Path
) -> None:
    """--report is in addition to stdout, never instead of it; both carry the
    same rendering — text, and json via the --json fold (ADR-0001)."""
    repo, lock = sealed
    text = tmp_path / "nested" / "reported.txt"
    as_json = tmp_path / "reported.json"

    plain = _verify(lock, repo, "--report", str(text))
    folded = _verify(lock, repo, "--json", "--report", str(as_json))

    assert plain.exit_code == ExitCode.FINDINGS
    assert "error fake/one: one fired" in plain.stdout
    # stdout and the file are the same rendering, byte for byte.
    assert text.read_text(encoding="utf-8") == plain.stdout
    document = json.loads(as_json.read_text(encoding="utf-8"))
    assert document == json.loads(folded.stdout)
    assert [f["rule_id"] for f in document["findings"]] == ["fake/one", "fake/two"]


def test_sarif_flows_through_the_same_pipeline(sealed: tuple[Path, Path], fake_rules: None) -> None:
    repo, lock = sealed

    result = _verify(lock, repo, "--format", "sarif")

    document = json.loads(result.stdout)
    assert [r["ruleId"] for r in document["runs"][0]["results"]] == ["fake/one", "fake/two"]
    assert result.exit_code == ExitCode.FINDINGS


def test_the_default_packet_is_discovered_from_the_build_dir(tmp_path: Path) -> None:
    """Discovery is what this pins, so the run narrows to one rule with nothing
    to say over the empty diff — the store is not an implementing repo and the
    observation rules would rightly complain about it."""
    with _cwd(tmp_path / "cwd") as cwd:
        store, out = _seal(tmp_path, "--format", "json")

        result = runner.invoke(
            app, ["verify", "--repo", str(store), "--diff-base", "HEAD", "--rule", "verify/scope"]
        )

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == _CLEAN_ADVISORY
    assert (cwd / out / "packet.lock").is_file()


def test_two_sealed_packets_are_a_usage_error_not_a_guess(tmp_path: Path) -> None:
    with _cwd(tmp_path / "cwd"):
        store, out = _seal(tmp_path, "--format", "json")
        shutil.copytree(out, out.parent / "m2")

        result = runner.invoke(app, ["verify", "--repo", str(store), "--diff-base", "HEAD"])

    assert result.exit_code == ExitCode.USAGE
    assert "--packet" in result.stderr
    assert "m1" in result.stderr
    assert "m2" in result.stderr


def test_an_unresolvable_diff_base_is_a_usage_error(sealed: tuple[Path, Path]) -> None:
    repo, lock = sealed

    result = runner.invoke(
        app, ["verify", "--packet", str(lock), "--repo", str(repo), "--diff-base", "no-such-ref"]
    )

    assert result.exit_code == ExitCode.USAGE
    assert "no-such-ref" in result.stderr
    assert result.stdout == ""


# ------------------------------------------------------------------- the rules
#
# The packets here are hand-built and sealed through the same two files
# `load_sealed_packet` reads — the packet's on-disk contract — because what a
# rule consumes is the sealed shape, not a store; shaping an element per rule
# is the point, and no fixture system holds these states. The one end-to-end
# run at the bottom uses the real `ab packet --seal` against `clean/` instead.

_CORE = Component(
    id="component:core",
    title="Core",
    state=State.SPECIFIED,
    level=ComponentLevel.COMPONENT,
    implemented_by=("code#src/core",),
)
_RISKY = Component(
    id="component:risky",
    title="Risky",
    state=State.UNKNOWN,
    level=ComponentLevel.COMPONENT,
    implemented_by=("code#src/risky",),
)
_DONE_WHEN = "behavior:thing#obs-1"
"""What a milestone's done_when names now: an observation id, not a criterion
record of its own."""

_CLEAN_STEPS = '''"""Step definitions for milestone:m1's scenarios."""

# behavior:order-cancelled#obs-1
def test_order_reads_cancelled():
    assert cancelled

# behavior:order-cancelled#obs-2
def test_nothing_for_the_order_remains_in_the_cache():
    assert not cached

# behavior:order-cancelled#obs-3
def test_the_event_carries_the_reason():
    assert reason
'''


def _full(element: Element) -> PacketElement:
    """A packet element at full fidelity: the element as built, every field."""
    return PacketElement(
        ref=element.id, fidelity=Fidelity.FULL, element=element.model_dump(mode="json")
    )


def _seal_pair(tmp_path: Path, packet: Packet, *, scenarios: dict[str, str] | None) -> Path:
    """A sealed pair on disk for ``packet``, its lock digesting ``scenarios``."""
    out = tmp_path / "packet"
    out.mkdir()
    (out / "packet.json").write_text(packet.model_dump_json(indent=2) + "\n", encoding="utf-8")
    lock = PacketLock(design_rev="0" * 40, observations_digest=observations_digest(scenarios or {}))
    (out / "packet.lock").write_text(lock.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return out / "packet.lock"


def _context_for(
    tmp_path: Path,
    packet: Packet,
    *,
    repos: tuple[Path, ...],
    scenarios: dict[str, str] | None = None,
    diff_base: str = "HEAD",
) -> verify.VerifyContext:
    """The context a rule sees: the packet sealed on disk, loaded back, plus
    each repo's diff — ``diff_base`` picks whether the repos carry a change."""
    brief, lock = verify.load_sealed_packet(_seal_pair(tmp_path, packet, scenarios=scenarios))
    return verify.context_for(brief, lock, diff_base=diff_base, repos=repos)


def _diff_repo(
    tmp_path: Path, name: str, committed: dict[str, str], change: dict[str, str]
) -> Path:
    """An implementing repo whose diff since ``HEAD~1`` is exactly ``change``."""
    repo = _repo(tmp_path, name, committed)
    for rel, content in change.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c2")
    return repo


def _rule(ctx: verify.VerifyContext, rule_id: str) -> tuple[Finding, ...]:
    """One rule's findings over ``ctx``, isolated from the other six."""
    return verify.run_rules(ctx, include=frozenset({rule_id})).findings


def test_the_eight_rules_are_registered_with_explanations() -> None:
    """The spec's ids, in the spec's order, each with an ``--explain`` text:
    ``finding()`` already refuses an unregistered id, this pins the surface."""
    assert list(verify.VERIFY_RULES) == [
        "verify/scope",
        "verify/out-of-scope",
        "verify/unknown-basis",
        "verify/interface-code",
        "verify/done-when",
        "verify/scenarios-unmodified",
        "verify/step-assertions",
        "verify/observations",
    ]
    assert set(verify.VERIFY_RULES) <= RULES.keys()


# ------------------------------------------------------------- verify/scope


def test_a_changed_file_outside_every_in_scope_component_is_a_finding(
    tmp_path: Path,
) -> None:
    packet = Packet(milestone="milestone:m", design="design:acme", elements=(_full(_CORE),))
    repo = _diff_repo(tmp_path, "code", {"src/core/api.py": "one\n"}, {"README.md": "words\n"})

    findings = _rule(
        _context_for(tmp_path, packet, repos=(repo,), diff_base="HEAD~1"), "verify/scope"
    )

    assert [f.message for f in findings] == [
        f"README.md in {repo} maps to no component the packet puts in scope"
    ]
    assert findings[0].severity is Severity.ERROR
    assert findings[0].source == "README.md"


def test_an_implementation_in_another_repo_does_not_cover_a_changed_file(
    tmp_path: Path,
) -> None:
    """``implemented_by``'s repo half names the ``--repo`` an entry speaks for:
    the same relative path under the wrong repo is leakage, not coverage — and
    under the right one, quiet, which is this pair's clean side."""
    acme = Component(
        id="component:core",
        title="Core",
        state=State.SPECIFIED,
        level=ComponentLevel.COMPONENT,
        implemented_by=("acme/core#src/core",),
    )
    packet = Packet(milestone="milestone:m", design="design:acme", elements=(_full(acme),))
    core = _diff_repo(
        tmp_path, "acme/core", {"src/core/api.py": "one\n"}, {"src/core/api.py": "two\n"}
    )
    elsewhere = _diff_repo(
        tmp_path, "elsewhere", {"src/core/api.py": "one\n"}, {"src/core/api.py": "two\n"}
    )

    findings = _rule(
        _context_for(tmp_path, packet, repos=(core, elsewhere), diff_base="HEAD~1"), "verify/scope"
    )

    assert [f.source for f in findings] == ["src/core/api.py"]
    assert str(elsewhere) in findings[0].message


def test_a_bare_implementation_path_applies_to_every_repo(tmp_path: Path) -> None:
    """``implemented_by`` with no ``#`` names no repo: the single-repo
    spelling, where ``src/core`` is already unambiguous."""
    bare = Component(
        id="component:core",
        title="Core",
        state=State.SPECIFIED,
        level=ComponentLevel.COMPONENT,
        implemented_by=("src/core",),
    )
    packet = Packet(milestone="milestone:m", design="design:acme", elements=(_full(bare),))
    repo = _diff_repo(
        tmp_path,
        "code",
        {"src/core/api.py": "one\n"},
        {"src/core/api.py": "two\n", "README.md": "words\n"},
    )

    findings = _rule(
        _context_for(tmp_path, packet, repos=(repo,), diff_base="HEAD~1"), "verify/scope"
    )

    assert [f.source for f in findings] == ["README.md"]


# ------------------------------------------------------- verify/out-of-scope


def test_building_an_out_of_scope_component_is_a_finding(tmp_path: Path) -> None:
    """A full run, not the isolated one: the change maps — to a component the
    packet carries — so verify/scope must stay quiet. That the two rules are
    distinct is exactly what this fixture pins."""
    frozen = Component(
        id="component:frozen",
        title="Frozen",
        state=State.OUT_OF_SCOPE,
        level=ComponentLevel.COMPONENT,
        implemented_by=("code#src/frozen",),
    )
    packet = Packet(
        milestone="milestone:m", design="design:acme", elements=(_full(_CORE), _full(frozen))
    )
    repo = _diff_repo(
        tmp_path,
        "code",
        {"src/core/api.py": "one\n", "src/frozen/old.py": "one\n"},
        {"src/frozen/thing.py": "new\n"},
    )

    result = verify.run_rules(_context_for(tmp_path, packet, repos=(repo,), diff_base="HEAD~1"))

    assert [(f.rule_id, f.ref) for f in result.findings] == [
        ("verify/out-of-scope", "component:frozen")
    ]
    assert "src/frozen/thing.py" in result.findings[0].message
    assert result.findings[0].severity is Severity.ERROR


def test_a_change_under_the_in_scope_component_leaves_the_frozen_one_alone(
    tmp_path: Path,
) -> None:
    frozen = Component(
        id="component:frozen",
        title="Frozen",
        state=State.OUT_OF_SCOPE,
        level=ComponentLevel.COMPONENT,
        implemented_by=("code#src/frozen",),
    )
    packet = Packet(
        milestone="milestone:m", design="design:acme", elements=(_full(_CORE), _full(frozen))
    )
    repo = _diff_repo(tmp_path, "code", {"src/core/api.py": "one\n"}, {"src/core/api.py": "two\n"})

    result = verify.run_rules(_context_for(tmp_path, packet, repos=(repo,), diff_base="HEAD~1"))

    assert result.findings == ()


# -------------------------------------------------------- verify/unknown-basis


def test_building_on_an_unknown_component_is_a_finding(tmp_path: Path) -> None:
    packet = Packet(milestone="milestone:m", design="design:acme", elements=(_full(_RISKY),))
    repo = _diff_repo(tmp_path, "code", {"src/risky/a.py": "one\n"}, {"src/risky/a.py": "two\n"})

    findings = _rule(
        _context_for(tmp_path, packet, repos=(repo,), diff_base="HEAD~1"), "verify/unknown-basis"
    )

    assert [f.ref for f in findings] == ["component:risky"]
    assert "src/risky/a.py" in findings[0].message
    assert findings[0].severity is Severity.ERROR


def test_a_decision_must_hold_names_covers_the_unknown(tmp_path: Path) -> None:
    answer = Decision(
        id="decision:answer",
        title="Recorded answer",
        state=State.SPECIFIED,
        choice="Risky stays as it is, and we live with it.",
        applies_to=("component:risky",),
    )
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(_RISKY), _full(answer)),
        must_hold=("decision:answer",),
    )
    repo = _diff_repo(tmp_path, "code", {"src/risky/a.py": "one\n"}, {"src/risky/a.py": "two\n"})

    findings = _rule(
        _context_for(tmp_path, packet, repos=(repo,), diff_base="HEAD~1"), "verify/unknown-basis"
    )

    assert findings == ()


def test_a_decision_only_carried_is_not_coverage(tmp_path: Path) -> None:
    """``must_hold`` naming the decision is what makes it an answer. A packet
    that merely carries one — hand-narrowed, or pulled in as a ring — cannot
    launder an unknown with it."""
    answer = Decision(
        id="decision:answer",
        title="Recorded answer",
        state=State.SPECIFIED,
        choice="Risky stays as it is, and we live with it.",
        applies_to=("component:risky",),
    )
    packet = Packet(
        milestone="milestone:m", design="design:acme", elements=(_full(_RISKY), _full(answer))
    )
    repo = _diff_repo(tmp_path, "code", {"src/risky/a.py": "one\n"}, {"src/risky/a.py": "two\n"})

    findings = _rule(
        _context_for(tmp_path, packet, repos=(repo,), diff_base="HEAD~1"), "verify/unknown-basis"
    )

    assert [f.ref for f in findings] == ["component:risky"]


# ------------------------------------------------------ verify/interface-code


def test_an_interface_in_scope_that_names_no_implementation_is_a_finding(tmp_path: Path) -> None:
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(Interface(id="interface:sync", title="Sync", style=InterfaceStyle.CALL)),),
    )
    repo = _repo(tmp_path, "code", {"src/core/api.py": "one\n"})

    findings = _rule(_context_for(tmp_path, packet, repos=(repo,)), "verify/interface-code")

    assert [f.ref for f in findings] == ["interface:sync"]
    assert "implemented_by" in findings[0].message
    assert findings[0].severity is Severity.ERROR


def test_a_named_contract_test_no_repo_holds_is_a_finding(tmp_path: Path) -> None:
    interface = Interface(
        id="interface:sync",
        title="Sync",
        style=InterfaceStyle.CALL,
        implemented_by=("tests/test_sync.py",),
    )
    packet = Packet(milestone="milestone:m", design="design:acme", elements=(_full(interface),))
    repo = _repo(tmp_path, "code", {"src/core/api.py": "one\n"})

    findings = _rule(_context_for(tmp_path, packet, repos=(repo,)), "verify/interface-code")

    assert [f.ref for f in findings] == ["interface:sync"]
    assert "tests/test_sync.py" in findings[0].message


def test_a_named_file_that_is_not_a_test_is_a_finding(tmp_path: Path) -> None:
    interface = Interface(
        id="interface:sync",
        title="Sync",
        style=InterfaceStyle.CALL,
        implemented_by=("tests/test_sync.py",),
    )
    packet = Packet(milestone="milestone:m", design="design:acme", elements=(_full(interface),))
    repo = _repo(tmp_path, "code", {"tests/test_sync.py": "# TODO\n"})

    findings = _rule(_context_for(tmp_path, packet, repos=(repo,)), "verify/interface-code")

    assert [f.ref for f in findings] == ["interface:sync"]
    assert "nothing that looks like a test" in findings[0].message


def test_an_existing_test_shaped_contract_test_is_quiet(tmp_path: Path) -> None:
    interface = Interface(
        id="interface:sync",
        title="Sync",
        style=InterfaceStyle.CALL,
        implemented_by=("tests/test_sync.py",),
    )
    packet = Packet(milestone="milestone:m", design="design:acme", elements=(_full(interface),))
    repo = _repo(tmp_path, "code", {"tests/test_sync.py": "def test_sync():\n    assert True\n"})

    findings = _rule(_context_for(tmp_path, packet, repos=(repo,)), "verify/interface-code")

    assert findings == ()


def test_an_interface_behind_the_seam_is_not_the_change_to_judge(tmp_path: Path) -> None:
    """A contract-fidelity neighbour is the ring around the work, not the work:
    the rule judges interfaces the packet carries at full fidelity only."""
    neighbour = PacketElement(
        ref="interface:sync",
        fidelity=Fidelity.CONTRACT,
        element=Interface(id="interface:sync", title="Sync", style=InterfaceStyle.CALL).model_dump(
            mode="json"
        ),
    )
    packet = Packet(milestone="milestone:m", design="design:acme", elements=(neighbour,))
    repo = _repo(tmp_path, "code", {"src/core/api.py": "one\n"})

    findings = _rule(_context_for(tmp_path, packet, repos=(repo,)), "verify/interface-code")

    assert findings == ()


# ----------------------------------------------------------- verify/done-when


def test_a_done_when_observation_nothing_references_is_a_finding(tmp_path: Path) -> None:
    """The ``.feature`` file names the observation in its own Scenario header and
    still does not count: scenarios are generated, step definitions are what
    somebody writes."""
    scenarios = {"thing.feature": f"Feature: Thing\n\n  Scenario: {_DONE_WHEN}\n"}
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(_CORE),),
        done_when=(_DONE_WHEN,),
    )
    repo = _repo(tmp_path, "code", dict(scenarios))

    findings = _rule(
        _context_for(tmp_path, packet, repos=(repo,), scenarios=scenarios), "verify/done-when"
    )

    assert [f.ref for f in findings] == ["behavior:thing"]
    assert _DONE_WHEN in findings[0].message
    assert findings[0].severity is Severity.ERROR


def test_a_done_when_observation_a_step_file_references_is_verified(tmp_path: Path) -> None:
    scenarios = {"thing.feature": "Feature: Thing\n"}
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(_CORE),),
        done_when=(_DONE_WHEN,),
    )
    repo = _repo(
        tmp_path, "code", dict(scenarios) | {"steps/steps.py": f'IDS = ("{_DONE_WHEN}",)\n'}
    )

    findings = _rule(
        _context_for(tmp_path, packet, repos=(repo,), scenarios=scenarios), "verify/done-when"
    )

    assert findings == ()


# ------------------------------------------------- verify/scenarios-unmodified


def test_scenario_files_matching_the_sealed_digest_are_not_a_finding(
    tmp_path: Path,
) -> None:
    scenarios = {"thing.feature": "Feature: Thing\n"}
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(_CORE),),
        done_when=(_DONE_WHEN,),
    )
    repo = _repo(tmp_path, "code", dict(scenarios))

    findings = _rule(
        _context_for(tmp_path, packet, repos=(repo,), scenarios=scenarios),
        "verify/scenarios-unmodified",
    )

    assert findings == ()


def test_modified_scenario_files_are_a_finding(tmp_path: Path) -> None:
    scenarios = {"thing.feature": "Feature: Thing\n"}
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(_CORE),),
        done_when=(_DONE_WHEN,),
    )
    repo = _repo(tmp_path, "code", {"thing.feature": "Feature: Thing, edited\n"})

    findings = _rule(
        _context_for(tmp_path, packet, repos=(repo,), scenarios=scenarios),
        "verify/scenarios-unmodified",
    )

    assert [f.rule_id for f in findings] == ["verify/scenarios-unmodified"]
    # The message carries both digests, so a human can tell which side moved.
    assert observations_digest({"thing.feature": "Feature: Thing, edited\n"}) in findings[0].message
    assert observations_digest(scenarios) in findings[0].message
    assert findings[0].severity is Severity.ERROR


# ------------------------------------------------------ verify/step-assertions


def test_a_step_file_without_assertions_is_a_finding(tmp_path: Path) -> None:
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(_CORE),),
        done_when=(_DONE_WHEN,),
    )
    repo = _repo(tmp_path, "code", {"steps/steps.py": f'IDS = ("{_DONE_WHEN}",)\n'})

    findings = _rule(_context_for(tmp_path, packet, repos=(repo,)), "verify/step-assertions")

    assert [f.source for f in findings] == ["steps/steps.py"]
    assert findings[0].severity is Severity.WARN  # a heuristic warns; --strict promotes


def test_a_step_file_with_assertions_is_not_a_finding(tmp_path: Path) -> None:
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(_CORE),),
        done_when=(_DONE_WHEN,),
    )
    steps = f'IDS = ("{_DONE_WHEN}",)\n\n\ndef check():\n    assert IDS\n'
    repo = _repo(tmp_path, "code", {"steps/steps.py": steps})

    findings = _rule(_context_for(tmp_path, packet, repos=(repo,)), "verify/step-assertions")

    assert findings == ()


# ------------------------------------------------------ verify/observations
#
# The one rule that asks the addendum §9 question over the packet's behaviors:
# does *something* check every `must` and `must_not` observation the packet
# carries in its satisfy and must-not-break lists? The evidence mechanism is
# `verify/done-when`'s — a repo file referencing the id — so the packets here
# are hand-built like the other rules'. One behavior carries the addendum
# §3.3's shape: a must, the double-write must_not, a should, a plain must.


_SESSION = Behavior(
    id="behavior:new-session",
    title="New session",
    trigger="A user starts a session.",
    observations=(
        Observation(
            id="behavior:new-session#obs-1",
            statement="The session is cached",
            at="resource:cache",
            outcome=Outcome.MUST,
            timing=Timing.IMMEDIATE,
        ),
        Observation(
            id="behavior:new-session#obs-2",
            statement="No audit entry appears",
            at="resource:audit-log",
            outcome=Outcome.MUST_NOT,
        ),
        Observation(
            id="behavior:new-session#obs-3",
            statement="The cache warms quickly",
            at="resource:cache",
            outcome=Outcome.SHOULD,
        ),
        Observation(
            id="behavior:new-session#obs-4",
            statement="The session appears in the list",
            at="component:sessions",
            outcome=Outcome.MUST,
        ),
    ),
)

_SATISFY = Packet(
    milestone="milestone:m",
    design="design:acme",
    elements=(_full(_SESSION),),
    satisfy=("behavior:new-session",),
)
_GUARDED = Packet(
    milestone="milestone:m",
    design="design:acme",
    elements=(_full(_SESSION),),
    must_not_break=("behavior:new-session",),
)


def test_an_evidenced_satisfy_observation_and_two_unguarded_ones(tmp_path: Path) -> None:
    """Three required observations, evidence for one: one ``checked``, two
    ``no_check`` errors naming the observation ids — the addendum's double-write
    example included, an absence nobody checks is as unguarded as a presence."""
    repo = _repo(
        tmp_path,
        "code",
        {
            "tests/test_session.py": "def test_cached():\n    assert True  # behavior:new-session#obs-1\n"
        },
    )

    findings = _rule(_context_for(tmp_path, _SATISFY, repos=(repo,)), "verify/observations")

    assert [f.message for f in findings] == [
        "nothing in the repos references behavior:new-session#obs-2 (must_not): "
        "no check guards this slice's new work",
        "nothing in the repos references behavior:new-session#obs-4 (must, immediate): "
        "no check guards this slice's new work",
    ]
    assert {f.severity for f in findings} == {Severity.ERROR}
    assert {f.ref for f in findings} == {"behavior:new-session"}


def test_every_satisfy_observation_evidenced_is_quiet(tmp_path: Path) -> None:
    evidence = {f"tests/obs-{n}.py": f"# behavior:new-session#obs-{n}\n" for n in (1, 2, 3, 4)}
    repo = _repo(tmp_path, "code", evidence)

    findings = _rule(_context_for(tmp_path, _SATISFY, repos=(repo,)), "verify/observations")

    assert findings == ()


def test_a_composed_behavior_is_context_not_a_rule_input(tmp_path: Path) -> None:
    """§4.2's one-hop rule: the behavior an included one composes rides in the
    packet so the agent sees the chain, but only the satisfy and must-not-break
    lists are verified — a composed behavior's own guard is the packet that
    includes it as work."""
    composed = Behavior(
        id="behavior:warm-cache",
        title="Warm the cache",
        trigger="A cache entry is read.",
        observations=(
            Observation(
                id="behavior:warm-cache#obs-1",
                statement="The cache is warm",
                at="resource:cache",
                outcome=Outcome.MUST,
            ),
        ),
    )
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(_SESSION), _full(composed)),
        satisfy=("behavior:new-session",),
    )
    repo = _repo(tmp_path, "code", {"app.py": "one\n"})

    findings = _rule(_context_for(tmp_path, packet, repos=(repo,)), "verify/observations")

    assert {f.ref for f in findings} == {"behavior:new-session"}
    assert "behavior:warm-cache" not in "".join(f.message for f in findings)


def test_a_satisfy_ref_the_packet_does_not_carry_is_skipped(tmp_path: Path) -> None:
    """A hand-narrowed or excluded packet can name a satisfy behavior it does
    not carry: there are no observations to verify, and the gap is ``ab
    check``'s dangling-ref finding — not a reason for verification to crash
    or to invent results."""
    packet = Packet(milestone="milestone:m", design="design:acme", satisfy=("behavior:elsewhere",))
    repo = _repo(tmp_path, "code", {"app.py": "one\n"})

    results = verify.observation_results(_context_for(tmp_path, packet, repos=(repo,)))

    assert results == ()


def test_a_must_not_break_observation_unguarded_warns_until_strict(tmp_path: Path) -> None:
    """A standing expectation this slice must not break, with nothing checking
    it: drift to surface, not a gate to fail the slice on — a warning, promoted
    by ``--strict`` like every warning. The ``should`` rides in the summary
    the same way it does over the satisfy set: §9 asks per observation, not
    per list."""
    repo = _repo(
        tmp_path,
        "code",
        {"tests/test_session.py": "# behavior:new-session#obs-1\n# behavior:new-session#obs-4\n"},
    )
    lock = _seal_pair(tmp_path, _GUARDED, scenarios={})

    lax = _verify(lock, repo, "--rule", "verify/observations")
    strict = _verify(lock, repo, "--rule", "verify/observations", "--strict")

    assert lax.exit_code == ExitCode.OK
    assert lax.stdout.splitlines() == [
        "warn verify/observations: nothing in the repos references "
        "behavior:new-session#obs-2 (must_not): "
        "no check guards a standing expectation this slice must not break",
        "advisory behavior:new-session#obs-3 (should, immediate): nothing references it",
        "1 should observation unchecked — advisory, never failed",
    ]
    assert strict.exit_code == ExitCode.FINDINGS


def test_a_should_observation_is_advisory_and_never_fails(tmp_path: Path) -> None:
    """§3.1: a ``should`` is reported as advisory — checked-ness noted inside
    the detail — and the unchecked count is surfaced in text and ``--json``,
    none of it in the exit code."""
    repo = _repo(
        tmp_path,
        "code",
        {
            "tests/test_session.py": (
                "# behavior:new-session#obs-1\n# behavior:new-session#obs-2\n"
                "# behavior:new-session#obs-4\n"
            )
        },
    )
    lock = _seal_pair(tmp_path, _SATISFY, scenarios={})

    text = _verify(lock, repo, "--rule", "verify/observations")
    as_json = _verify(lock, repo, "--rule", "verify/observations", "--format", "json")

    assert text.exit_code == ExitCode.OK
    assert text.stdout.splitlines() == [
        "advisory behavior:new-session#obs-3 (should, immediate): nothing references it",
        "1 should observation unchecked — advisory, never failed",
    ]
    assert as_json.exit_code == ExitCode.OK
    assert json.loads(as_json.stdout)["summary"] == {
        "unchecked_should": 1,
        "advisories": [
            {
                "observation": "behavior:new-session#obs-3",
                "evidence_ref": None,
                "timing": "immediate",
            }
        ],
    }


def test_a_checked_should_is_reported_without_a_count(tmp_path: Path) -> None:
    """Checked-ness rides inside the advisory detail, so a checked ``should``
    says where it is checked and does not pump the unchecked count."""
    repo = _repo(tmp_path, "code", {"tests/test_session.py": "# behavior:new-session#obs-3\n"})
    lock = _seal_pair(tmp_path, _SATISFY, scenarios={})

    result = _verify(lock, repo, "--rule", "verify/observations")

    assert result.exit_code == ExitCode.FINDINGS  # obs-1, obs-2, obs-4 are unguarded
    assert result.stdout.splitlines()[-1] == (
        "advisory behavior:new-session#obs-3 (should, immediate): checked by tests/test_session.py"
    )
    assert "unchecked" not in result.stdout


def test_effective_timing_comes_sealed_then_from_the_carried_resources(tmp_path: Path) -> None:
    """The timing reported with each result is the *effective* one: the value
    sealed into the packet wins (a real seal derives it through 51's helper
    against the whole design), and a hand-built packet falls back to the same
    §1.2 table over the resources the packet happens to carry."""
    stream = Resource(
        id="resource:events",
        title="Events",
        resource_kind=ResourceKind.STREAM,
        technology="Kafka",
    )
    behavior = Behavior(
        id="behavior:new-session",
        title="New session",
        trigger="A user starts a session.",
        observations=(
            Observation(
                id="behavior:new-session#obs-1",
                statement="An event is emitted",
                at="resource:events",
                outcome=Outcome.MUST,
            ),
            Observation(
                id="behavior:new-session#obs-2",
                statement="An uncached target stays immediate",
                at="resource:elsewhere",
                outcome=Outcome.MUST,
            ),
            Observation(
                id="behavior:new-session#obs-3",
                statement="A sealed value beats the authored one",
                at="resource:events",
                outcome=Outcome.MUST,
                timing=Timing.IMMEDIATE,
            ),
            Observation(
                id="behavior:new-session#obs-4",
                statement="No entry appears",
                at="resource:audit-log",
                outcome=Outcome.MUST_NOT,
            ),
        ),
    )
    carried = behavior.model_dump(mode="json")
    carried["observations"][2]["effective_timing"] = "eventual"  # what a real seal writes
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(
            PacketElement(ref="behavior:new-session", fidelity=Fidelity.FULL, element=carried),
            _full(stream),
        ),
        satisfy=("behavior:new-session",),
    )
    repo = _repo(tmp_path, "code", {"app.py": "one\n"})

    results = verify.observation_results(_context_for(tmp_path, packet, repos=(repo,)))

    assert [(r.observation, r.timing) for r in results] == [
        ("behavior:new-session#obs-1", Timing.EVENTUAL),
        ("behavior:new-session#obs-2", Timing.IMMEDIATE),
        ("behavior:new-session#obs-3", Timing.EVENTUAL),
        ("behavior:new-session#obs-4", None),
    ]


def test_the_run_records_one_row_per_observation(tmp_path: Path) -> None:
    """§8's second tuple over the observations: one row per observation of the
    packet's behavior sets, ``advisory`` for a ``should`` with its evidence
    when one exists. A ``done_when`` id is one of those observations now, so it
    rides in the same row rather than a criterion row beside it."""
    packet = Packet(
        milestone="milestone:m",
        design="design:acme",
        elements=(_full(_SESSION),),
        satisfy=("behavior:new-session",),
        done_when=("behavior:new-session#obs-1",),
    )
    repo = _repo(
        tmp_path,
        "code",
        {
            "tests/test_session.py": "def test_cached():\n    assert True  # behavior:new-session#obs-1\n"
        },
    )
    lock_path = _seal_pair(tmp_path, packet, scenarios={})
    brief, lock = verify.load_sealed_packet(lock_path)
    store = tmp_path / "store"
    store.mkdir()

    result = runner.invoke(
        app,
        [
            "--store",
            str(store),
            "verify",
            "--packet",
            str(lock_path),
            "--repo",
            str(repo),
            "--diff-base",
            "HEAD",
            "--rule",
            "verify/observations",
        ],
    )

    assert result.exit_code == ExitCode.FINDINGS  # obs-2 and obs-4 are unguarded
    (run,) = runstore.runs_for(store, runstore.packet_id(brief.milestone, lock.design_rev))
    assert run.results == (
        RunResult(
            observation="behavior:new-session#obs-1",
            result="checked",
            evidence_ref="tests/test_session.py",
        ),
        RunResult(observation="behavior:new-session#obs-2", result="no_check", evidence_ref=None),
        RunResult(observation="behavior:new-session#obs-3", result="advisory", evidence_ref=None),
        RunResult(observation="behavior:new-session#obs-4", result="no_check", evidence_ref=None),
    )


# ------------------------------------------------------------- end to end


def test_a_clean_reconciliation_against_the_clean_fixture_passes(tmp_path: Path) -> None:
    """The spec's end-to-end: a packet sealed for real from ``clean/``'s
    milestone, and a repo built to satisfy every rule at once — no rule has
    anything to say and the exit is OK. The slice's one ``should`` observation
    still reports as an advisory: that is visibility, never a finding."""
    _, out = _seal(tmp_path, "--format", "json", out=tmp_path / "packet")
    feature = (out / "features" / "order-cancelled.feature").read_text(encoding="utf-8")
    # The seal must actually have digested this file, or rule 6 would be
    # passing vacuously: pin the fixture before trusting the verdict.
    lock = PacketLock.model_validate_json((out / "packet.lock").read_text(encoding="utf-8"))
    assert lock.observations_digest == observations_digest({"order-cancelled.feature": feature})
    repo = _repo(
        tmp_path, "code", {"order-cancelled.feature": feature, "steps/test_steps.py": _CLEAN_STEPS}
    )

    result = runner.invoke(
        app,
        [
            "verify",
            "--packet",
            str(out / "packet.lock"),
            "--repo",
            str(repo),
            "--diff-base",
            "HEAD",
        ],
    )

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "advisory behavior:order-cancelled#obs-3 (should, eventual): checked by steps/test_steps.py"
    ]


# ------------------------------------------------------------------ the run store


def test_the_run_is_recorded_beside_the_design_store(
    tmp_path: Path, sealed: tuple[Path, Path]
) -> None:
    """``docs/tasks/58-run-store.md``: every verification run lands in the
    design store's ``build/runs.db`` — the packet id the issuance digest
    spells, the verified repo's HEAD, one row per observation: ``checked`` with
    the referencing file as evidence, ``no_check`` without one. Recorded
    whatever the verdict; a run with findings is still a run."""
    store, lock_path = sealed
    packet, lock = verify.load_sealed_packet(lock_path)
    feature = (lock_path.parent / "features" / "order-cancelled.feature").read_text(
        encoding="utf-8"
    )
    repo = _repo(
        tmp_path,
        "impl",
        {
            "order-cancelled.feature": feature,
            "tests/test_cancel.py": (
                "def test_cancel():\n    assert True  # behavior:order-cancelled#obs-1\n"
            ),
        },
    )

    result = runner.invoke(
        app,
        [
            "--store",
            str(store),
            "verify",
            "--packet",
            str(lock_path),
            "--repo",
            str(repo),
            "--diff-base",
            "HEAD",
        ],
    )

    # obs-2 has nothing referencing it: the run has findings, and is recorded
    # anyway. obs-3 is a `should`, so it lands as an advisory row instead.
    assert result.exit_code == ExitCode.FINDINGS
    (run,) = runstore.runs_for(store, runstore.packet_id(packet.milestone, lock.design_rev))
    assert run.commit_sha == current_rev(repo)
    assert run.results == (
        RunResult(
            observation="behavior:order-cancelled#obs-1",
            result="checked",
            evidence_ref="tests/test_cancel.py",
        ),
        RunResult(
            observation="behavior:order-cancelled#obs-2", result="no_check", evidence_ref=None
        ),
        RunResult(
            observation="behavior:order-cancelled#obs-3", result="advisory", evidence_ref=None
        ),
    )


def test_a_verify_with_nowhere_to_record_still_verifies(
    tmp_path: Path, sealed: tuple[Path, Path]
) -> None:
    """Verification is offline: when no design store can be located beside it,
    the run leaves no history — said on stderr, never swallowing the verdict."""
    _, lock_path = sealed
    repo = _repo(tmp_path, "impl", {"order-cancelled.feature": "Feature: x\n"})

    result = runner.invoke(
        app,
        [
            "--store",
            str(tmp_path / "nowhere"),
            "verify",
            "--packet",
            str(lock_path),
            "--repo",
            str(repo),
            "--diff-base",
            "HEAD",
        ],
    )

    assert result.exit_code == ExitCode.FINDINGS
    assert "not recorded" in result.stderr
    assert "nowhere" in result.stderr


def test_a_future_run_store_fails_the_verification_loudly(
    tmp_path: Path, sealed: tuple[Path, Path]
) -> None:
    """A ``runs.db`` left by a newer ``ab`` is refused rather than guessed at:
    the exit names the mismatch (4) before any report is printed."""
    store, lock_path = sealed
    db = store / "build" / "runs.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {runstore.USER_VERSION + 1}")
    conn.close()
    repo = _repo(tmp_path, "impl", {"app.py": "one\n"})

    result = runner.invoke(
        app,
        [
            "--store",
            str(store),
            "verify",
            "--packet",
            str(lock_path),
            "--repo",
            str(repo),
            "--diff-base",
            "HEAD",
        ],
    )

    assert result.exit_code == ExitCode.SCHEMA_MISMATCH
    assert "runs.db" in result.stderr
    assert result.stdout == ""
