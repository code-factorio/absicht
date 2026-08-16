"""``ab verify``'s scaffolding: the sealed packet, the diff, the rule plumbing.

``docs/tasks/40-verify-core.md`` builds the frame that
``docs/tasks/41-verify-rules.md`` hangs rules into, so what these tests pin is
everything around the rules:

- ``load_sealed_packet`` reads back exactly what ``ab packet --seal`` wrote —
  offline, no design store — and refuses what it cannot read back (a missing
  lock, a Markdown-only body) as a usage error naming the fix;
- the default ``--packet`` discovery refuses to guess: zero or two sealed
  packets under the build dir is a usage error, exactly one is used;
- ``context_for`` resolves one diff per ``--repo`` against ``--diff-base`` —
  the multi-repo shape the rules will read;
- ``--rule``/``--exclude-rule`` select which rules run (against fake rules
  registered for the test, since 41's real ones do not exist yet), an unknown
  id is a usage error, and ``--strict`` promotes the warnings that survive;
- ``--report`` writes the rendered report *in addition to* stdout, and an
  empty report stays silent on stdout while still writing the (empty) file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from absicht import verify
from absicht.cli import app
from absicht.cli._common import DEFAULT_PACKET_DIR, ExitCode
from absicht.findings import RULES, Finding, Severity, finding
from absicht.git import current_rev
from absicht.models import SCHEMA_VERSION, Packet, PacketLock

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"

# Hand-built stand-ins for a sealed pair: the plumbing under test needs the
# models' shapes, not a real seal.
_PACKET = Packet(milestone="milestone:m1")
_LOCK = PacketLock(design_rev="0" * 40, scenarios_digest="deadbeef")


def _git(repo: Path, *args: str) -> str:
    """Fixture plumbing: run git in ``repo``, failing loudly if git does."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def _init_repo(repo: Path) -> None:
    """Turn an existing directory into a one-commit git repository."""
    _git(repo, "init", "-q", "-b", "main")
    # A bare CI machine has no git identity, and commits must not try to sign.
    _git(repo, "config", "user.email", "tests@absicht.invalid")
    _git(repo, "config", "user.name", "absicht tests")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c1")


def _repo(tmp_path: Path, name: str, files: dict[str, str]) -> Path:
    """A one-commit git repository holding ``files`` — an implementing repo."""
    repo = tmp_path / name
    repo.mkdir()
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
    assert lock == PacketLock(
        schema_version=SCHEMA_VERSION,
        design_rev=current_rev(repo),
        scenarios_digest=packet.scenarios_digest,
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


def test_without_rules_the_report_is_an_empty_pass(
    sealed: tuple[Path, Path], tmp_path: Path
) -> None:
    """No rule bodies exist yet (41's job); the frame still has to answer OK,
    stay silent on stdout in text — the pass signal a human greps for — and
    honour --report even for an empty rendering."""
    repo, lock = sealed
    written = tmp_path / "reported.txt"

    plain = _verify(lock, repo, "--report", str(written))
    as_json = _verify(lock, repo, "--format", "json")

    assert plain.exit_code == ExitCode.OK
    assert plain.stdout == ""
    assert written.read_text(encoding="utf-8") == ""
    assert json.loads(as_json.stdout) == {"schema_version": SCHEMA_VERSION, "findings": []}


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
    # A warning alone passes; --strict is what promotes it.
    assert only_warn.exit_code == ExitCode.OK
    assert only_warn.stdout == "warn fake/two: two fired\n"
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
    with _cwd(tmp_path / "cwd") as cwd:
        store, out = _seal(tmp_path, "--format", "json")

        result = runner.invoke(app, ["verify", "--repo", str(store), "--diff-base", "HEAD"])

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""
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
