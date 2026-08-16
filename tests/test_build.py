"""``ab build``: fold the store into the one artifact everything downstream reads.

Every CLI case goes through the runner because the contract under test is the
exit code and the bytes on disk, and every ``--out`` names a ``tmp_path`` so no
case writes into the working directory.

What the spec (docs/tasks/20-build.md) pins, and these hold:

- **Determinism**: two builds over the same store are byte-identical, and the
  document's key order is ``Design``'s field declaration order — pydantic's
  default, confirmed rather than assumed, because nothing in the serializer
  forces it and ``--check``'s byte comparison inherits whatever order lands.
  The harder variant (clean checkout, varied ``PYTHONHASHSEED``) is a CI job
  to come, per docs/maintainers/verification.md; nothing here may make it
  impossible.
- A store with a ``LoadError`` fails the build rather than emitting a partial
  artifact: ``broken/``'s two unreadable files are the case.
- ``--check`` compares byte-for-byte against the file at ``--out``: identical
  is ``OK``, drifted or missing is ``FINDINGS`` — a missing artifact has
  trivially moved from nothing, and CI's drift gate must not pass on absence.
- ``--rev`` reads the store through git, the ``FileSource`` seam
  ``absicht.load`` left for it: the artifact at an old rev reflects that
  rev's tree, not the working tree.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

from absicht.build import _AtRevision, build, design_json
from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.models import SCHEMA_VERSION, Design

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures" / "systems"

# The fixtures that load cleanly. `broken/` cannot be built on purpose: its
# two unreadable files are the refusal case below, not a snapshot.
BUILDABLE = ("brownfield", "clean", "composite")


def _build_to(out: Path, *, store: Path = FIXTURES / "clean") -> None:
    result = runner.invoke(app, ["--store", str(store), "build", "--out", str(out)])
    assert result.exit_code == ExitCode.OK


@pytest.mark.parametrize("name", BUILDABLE)
def test_each_fixture_builds_to_its_snapshot(name: str, snapshot: SnapshotAssertion) -> None:
    """The golden artifacts: one snapshot per fixture system, so any change in
    what a build folds — a loader fix, a model field, an ordering — shows up
    as a reviewable diff of the document, not as a downstream surprise."""
    document = json.loads(design_json(build(FIXTURES / name)))

    assert document == snapshot


def test_two_builds_of_one_store_are_byte_identical(tmp_path: Path) -> None:
    """`clean/` carries the addendum kinds (a resource, behaviors with inline
    observations), so this is also the proof that `build` needs nothing new
    for them: it is generic over `Design`, and byte-identical output over a
    store containing the new kinds is that genericity holding."""

    first, second = tmp_path / "a" / "design.json", tmp_path / "b" / "design.json"

    for out in (first, second):
        _build_to(out)

    assert first.read_bytes() == second.read_bytes()


def test_the_documents_keys_are_designs_field_order() -> None:
    """The key order is a property of `models.py` alone, which is what lets a
    consumer index into the artifact without parsing it defensively."""
    text = design_json(build(FIXTURES / "clean"))

    assert list(json.loads(text)) == list(Design.model_fields)


def test_a_store_with_load_errors_fails_the_build_without_writing(tmp_path: Path) -> None:
    out = tmp_path / "build" / "design.json"

    result = runner.invoke(app, ["--store", str(FIXTURES / "broken"), "build", "--out", str(out)])

    assert result.exit_code == ExitCode.FINDINGS
    # Both unreadable files are named, and the way out is `ab check` — the
    # findings command, not a partial build to inspect.
    assert "requirements/garbage.md" in result.stderr
    assert "stories/bad-anchor.md" in result.stderr
    assert "ab check" in result.stderr
    assert not out.exists()


def test_stdout_prints_the_artifact_and_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "design.json"
    argv = ["--store", str(FIXTURES / "clean"), "build", "--out", str(out), "--stdout"]

    plain = runner.invoke(app, argv)
    as_json = runner.invoke(app, [*argv, "--json"])

    assert plain.exit_code == ExitCode.OK
    # `--json` is a no-op here by construction: the document on stdout is
    # already machine output, `schema_version` first.
    assert plain.stdout == as_json.stdout
    # Byte-identical to what a write would have produced, newline included.
    assert plain.stdout == design_json(build(FIXTURES / "clean"))
    assert json.loads(plain.stdout)["schema_version"] == SCHEMA_VERSION
    assert not out.exists()


def test_writing_creates_parent_directories_as_needed(tmp_path: Path) -> None:
    out = tmp_path / "deep" / "nested" / "design.json"

    result = runner.invoke(app, ["--store", str(FIXTURES / "clean"), "build", "--out", str(out)])

    assert result.exit_code == ExitCode.OK
    assert out.read_text(encoding="utf-8") == design_json(build(FIXTURES / "clean"))
    assert result.stdout.strip() == f"wrote {out}"


def test_check_against_a_fresh_artifact_is_ok(tmp_path: Path) -> None:
    out = tmp_path / "design.json"
    _build_to(out)

    result = runner.invoke(
        app, ["--store", str(FIXTURES / "clean"), "build", "--out", str(out), "--check"]
    )

    assert result.exit_code == ExitCode.OK
    assert f"{out} is up to date" in result.stdout


def test_check_against_a_drifted_artifact_is_findings(tmp_path: Path) -> None:
    out = tmp_path / "design.json"
    _build_to(out)
    drifted = out.read_bytes() + b"\n"
    out.write_bytes(drifted)

    result = runner.invoke(
        app, ["--store", str(FIXTURES / "clean"), "build", "--out", str(out), "--check"]
    )

    assert result.exit_code == ExitCode.FINDINGS
    assert f"stale: {out} differs from a fresh build" in result.stdout
    assert f"run ab build --out {out} to refresh" in result.stdout
    # Checking never writes: the drifted bytes are what the next run sees too.
    assert out.read_bytes() == drifted


def test_check_with_no_artifact_on_disk_is_findings(tmp_path: Path) -> None:
    """A missing artifact has moved from nothing. The alternative — `OK`
    because there was nothing to diff against — is the drift gate passing on
    exactly the case it exists to catch."""

    result = runner.invoke(
        app,
        [
            "--store",
            str(FIXTURES / "clean"),
            "build",
            "--out",
            str(tmp_path / "design.json"),
            "--check",
        ],
    )

    assert result.exit_code == ExitCode.FINDINGS
    assert "does not exist yet" in result.stdout


def test_json_envelopes_the_write_and_the_check(tmp_path: Path) -> None:
    out = tmp_path / "design.json"
    argv = ["--store", str(FIXTURES / "clean"), "build", "--out", str(out)]

    ahead = runner.invoke(app, ["--json", *argv])
    fresh = runner.invoke(app, [*argv, "--check", "--json"])
    out.write_bytes(b"{}\n")
    stale = runner.invoke(app, [*argv, "--check", "--json"])

    assert ahead.exit_code == ExitCode.OK
    assert fresh.exit_code == ExitCode.OK
    assert stale.exit_code == ExitCode.FINDINGS
    assert json.loads(ahead.stdout) == {"schema_version": SCHEMA_VERSION, "out": str(out)}
    assert json.loads(fresh.stdout) == {
        "schema_version": SCHEMA_VERSION,
        "out": str(out),
        "stale": False,
    }
    assert json.loads(stale.stdout)["stale"] is True


def _git(repo: Path, *args: str) -> str:
    """Fixture plumbing: run git in ``repo``, failing loudly if it does."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def history(tmp_path: Path) -> tuple[Path, str]:
    """A throwaway repo whose store moved after its first commit, whose sha is
    the probe: a build at it must fold the tree as it stood then, not as the
    working tree sits now.

    Not tests/test_git.py's repo — that store's files are placeholders a build
    cannot parse. The `components/nested/` file proves the adapter flattens
    nothing git lists recursively: `load`'s walk is one directory deep.
    """
    repo = tmp_path / "repo"
    store = repo / ".absicht"
    (store / "components" / "nested").mkdir(parents=True)
    (store / "system.yaml").write_text("id: system:tiny\ntitle: Tiny\n", encoding="utf-8")

    def component(title: str) -> None:
        (store / "components" / "cancellation.md").write_text(
            f"---\nid: component:cancellation\ntitle: {title}\n---\n", encoding="utf-8"
        )

    component("Cancellation")
    (store / "components" / "nested" / "deep.md").write_text(
        "---\nid: component:deep\ntitle: Deep\n---\n", encoding="utf-8"
    )
    _git(repo, "init", "-q", "-b", "main")
    # A bare CI machine has no git identity, and commits must not try to sign.
    _git(repo, "config", "user.email", "tests@absicht.invalid")
    _git(repo, "config", "user.name", "absicht tests")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c1")
    first = _git(repo, "rev-parse", "HEAD").strip()
    component("Cancellation, retitled")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c2")
    return store, first


def test_build_at_a_rev_folds_that_revs_tree(history: tuple[Path, str]) -> None:
    store, first = history

    at_rev = build(store, rev=first)
    on_disk = build(store)

    assert [c.title for c in at_rev.components] == ["Cancellation"]
    assert [c.title for c in on_disk.components] == ["Cancellation, retitled"]


def test_the_cli_builds_the_artifact_at_a_rev(history: tuple[Path, str]) -> None:
    store, first = history

    result = runner.invoke(app, ["--store", str(store), "--rev", first, "build", "--stdout"])

    assert result.exit_code == ExitCode.OK
    document = json.loads(result.stdout)
    assert document["components"][0]["title"] == "Cancellation"


def test_a_rev_that_does_not_exist_is_a_usage_error(history: tuple[Path, str]) -> None:
    store, _ = history

    result = runner.invoke(
        app, ["--store", str(store), "--rev", "no-such-ref", "build", "--stdout"]
    )

    assert result.exit_code == ExitCode.USAGE
    assert "no-such-ref" in result.stderr


def test_the_git_source_answers_loads_three_questions(history: tuple[Path, str]) -> None:
    """The adapter is `load`'s only view of a revision, so its contract is
    pinned directly — including the race-only branch, where a file listed then
    unreadable surfaces as the `OSError` load already translates."""
    store, first = history
    source = _AtRevision(Path(".absicht"), first, store.parent)

    assert source.exists(Path(".absicht/system.yaml"))
    assert source.exists(Path(".absicht/components"))  # a tree, not only a blob
    assert not source.exists(Path(".absicht/questions"))
    assert source.list_files(Path(".absicht/components")) == (
        Path(".absicht/components/cancellation.md"),
    )
    assert source.read_text(Path(".absicht/system.yaml")) == "id: system:tiny\ntitle: Tiny\n"
    with pytest.raises(OSError, match="absent at the revision"):
        source.read_text(Path(".absicht/never-existed.md"))
