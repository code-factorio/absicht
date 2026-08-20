"""``ab packet MILESTONE``: the brief assembled, rendered and written to disk.

The assembly itself is ``tests/test_packet.py``'s; what is pinned here is the
command around it:

- ``--format md`` is one document with the spec's sections: scope at full
  detail, the two behavior sections between them, the contract ring summarized
  to a line each, and ``must_hold``/``may_decide``/``unresolved``/
  ``rejections``/``done_when`` as their own sections with emptiness spelled
  out — an agent has to *see* that nothing constrains it;
- ``--format json`` writes the ``Packet`` model dump, ``format_version`` first;
- the default ``--out`` is ``.absicht/build/packets/<milestone-slug>`` — the
  slug, not the whole ``kind:slug`` id;
- ``--stdout`` is byte-identical to the file a write would produce and writes
  no packet — but the ``.feature`` files still land, relative to the cwd,
  because they are what a seal digests and not part of the body;
- ``--seal`` writes ``packet.lock`` whose ``design_rev`` is the store repo's
  current (or ``--rev``'s) commit and whose ``observations_digest`` is
  ``absicht.gherkin``'s over the files just rendered — compared against an
  independently computed digest, never against the CLI's own output;
- ``--rev`` builds from that revision's tree, not the working tree's;
- the judgement calls are pinned rather than left open: ``--stdout --seal`` is
  a usage error (a seal with nowhere durable to put the lock), ``--no-features
  --seal`` too (a digest over zero files), a milestone nothing names is
  ``USAGE`` and a milestone that names no scope is ``FINDINGS``;
- ``--include``/``--exclude`` are gone, so a packet's contents are the
  milestone's own selection and nothing a caller narrowed by hand;
- issuance is recorded in the store's run store for every assembly, and the
  same store re-packeted lands byte-identical artifacts — the premise under
  regenerating a packet rather than storing one.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

from absicht import runstore
from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.gherkin import observations_digest, render_feature
from absicht.git import current_rev, resolve_rev
from absicht.load import load_store
from absicht.models.design import FORMAT_VERSION, Behavior
from absicht.resolve import Index, resolve

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"

V1_OUTCOME = "A customer can cancel an order that has not shipped."
V2_OUTCOME = "A customer can cancel any order that has not shipped, cheaply."

# The selection assemble() makes for clean/m1 at horizon 1 — what both formats
# must carry, independent of how each spells it.
ELEMENTS = {
    "milestone:m1": "full",
    "component:orders": "full",
    "component:cancellation": "full",
    "behavior:order-cancelled": "full",
    "decision:event-log": "full",
    "quality:cancel-latency": "full",
    "component:acme": "contract",
    "constraint:gdpr-erasure": "contract",
    "data:order": "contract",
    "interface:order-events": "contract",
    "library:pydantic": "contract",
    "req:cancel-orders": "contract",
    "resource:order-cache": "contract",
    "resource:order-stream": "contract",
}
DONE_WHEN = ["behavior:order-cancelled#obs-1"]
FEATURE = "order-cancelled.feature"


_SCRATCH: Path = CLEAN
"""The store ``_packet`` targets when no test names one. The autouse fixture
below points it at a fresh copy of the clean fixture per test; the module
default only covers direct imports of the helper outside a test run."""


def _packet(*flags: str, store: Path | None = None, milestone: str = "milestone:m1") -> Any:
    """``ab packet`` against the clean fixture — a per-test copy of it, because
    the command records issuance under the store's own ``build/`` and the
    shared fixture is read-only."""
    root = store if store is not None else _SCRATCH
    return runner.invoke(app, ["--store", str(root), "packet", milestone, *flags])


@pytest.fixture(autouse=True)
def scratch(tmp_path: Path) -> Iterator[Path]:
    """The clean fixture copied once per test, as ``_packet``'s default store.

    Issuance recording made ``ab packet`` a store-writing command: pointed at
    the shared fixture it would leave ``build/runs.db`` behind in it, and every
    later copy of the fixture would carry stale history into its assertions."""
    global _SCRATCH
    copied = tmp_path / "clean"
    shutil.copytree(CLEAN, copied)
    _SCRATCH = copied
    try:
        yield copied
    finally:
        _SCRATCH = CLEAN


def _body(out: Path, *flags: str) -> str:
    result = _packet("--out", str(out), *flags)
    assert result.exit_code == ExitCode.OK
    return (out / "packet.md").read_text(encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    """Fixture plumbing: run git in ``repo``, failing loudly if git does."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@contextmanager
def _cwd(directory: Path) -> Iterator[Path]:
    """Run with the cwd moved into a directory the test owns, so a relative
    default ``--out`` (or ``--features-dir`` under ``--stdout``) lands there —
    typer's CliRunner has no isolated filesystem of its own."""
    directory.mkdir(parents=True, exist_ok=True)
    origin = Path.cwd()
    os.chdir(directory)
    try:
        yield directory
    finally:
        os.chdir(origin)


def _as_repo(store: Path) -> None:
    """Turn a copy of a fixture into a one-commit git repository."""
    _git(store, "init", "-q", "-b", "main")
    # A bare CI machine has no git identity, and commits must not try to sign.
    _git(store, "config", "user.email", "tests@absicht.invalid")
    _git(store, "config", "user.name", "absicht tests")
    _git(store, "config", "commit.gpgsign", "false")
    _git(store, "add", "-A")
    _git(store, "commit", "-qm", "c1")


def _retitle_outcome(store: Path, outcome: str) -> None:
    """Move the milestone in the working tree past what the last commit holds."""
    milestone = store / "milestones" / "m1.md"
    milestone.write_text(
        milestone.read_text(encoding="utf-8").replace(V1_OUTCOME, outcome), encoding="utf-8"
    )


def _unscoped(store: Path) -> Path:
    """A milestone that names no scope, added to a store that otherwise loads.

    ``broken/``'s own ``milestone:unscoped`` cannot serve here: three of that
    fixture's files fail to load on purpose, and the command refuses a store
    it cannot read whole before it ever reaches assembly."""
    (store / "milestones" / "unscoped.md").write_text(
        "---\n"
        "id: milestone:unscoped\n"
        "title: Unscoped\n"
        "state: specified\n"
        "outcome: Something gets better.\n"
        "---\n",
        encoding="utf-8",
    )
    return store


# ------------------------------------------------------------- the two formats


def test_md_is_one_document_with_the_spec_sections(tmp_path: Path) -> None:
    out = tmp_path / "packet"

    result = _packet("--out", str(out))

    assert result.exit_code == ExitCode.OK
    assert result.stdout == f"wrote {out}/packet.md\nwrote {out}/features (1 feature file)\n"
    document = (out / "packet.md").read_text(encoding="utf-8")
    assert document.startswith("# Packet: Cancellation\n")
    assert f"`milestone:m1` — {V1_OUTCOME}" in document
    # Scope at full detail: the component's own fields, not a summary line.
    assert "### Cancellation" in document
    assert (
        "- responsibility: Decide whether an order may still be cancelled, and do it." in document
    )
    assert "- parent: component:orders" in document
    # The contract ring summarized to one line per neighbour.
    assert "- `interface:order-events` — Order events" in document
    assert "- `req:cancel-orders` — Cancel an order" in document
    # The obligations as their own sections, the empty ones spelled out.
    for heading in ("## Must hold", "## May decide", "## Unresolved", "## Rejections"):
        assert heading in document
    assert "(none)" in document
    assert "## Done when" in document
    assert f"- `{DONE_WHEN[0]}`" in document
    # The pointer to the Gherkin that was rendered beside the body.
    assert "`features/`" in document
    assert (out / "features" / FEATURE).is_file()


def test_the_md_document_is_snapshotted(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    """The golden document: every line of the rendering is contract, so a
    formatting change arrives as a reviewable diff, not a downstream surprise."""

    assert _body(tmp_path / "packet") == snapshot


def test_json_writes_the_model_dump_format_version_first(tmp_path: Path) -> None:
    out = tmp_path / "packet"

    result = _packet("--out", str(out), "--format", "json")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == f"wrote {out}/packet.json\nwrote {out}/features (1 feature file)\n"
    document = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert document["format_version"] == FORMAT_VERSION
    assert document["milestone"] == "milestone:m1"
    assert document["outcome"] == V1_OUTCOME
    assert {element["ref"]: element["fidelity"] for element in document["elements"]} == ELEMENTS
    assert document["done_when"] == DONE_WHEN
    # The format names the body's file; a json packet never writes a .md.
    assert not (out / "packet.md").exists()


def test_json_folds_into_a_default_format_only(tmp_path: Path) -> None:
    """``--json`` selects the json member of ``--format`` while ``--format`` sits
    at its default, and an explicit ``--format md`` wins over it (ADR-0001)."""

    folded = _packet("--json", "--out", str(tmp_path / "folded"))
    explicit = _packet("--format", "md", "--json", "--out", str(tmp_path / "explicit"))

    assert folded.exit_code == ExitCode.OK
    assert explicit.exit_code == ExitCode.OK
    assert (tmp_path / "folded" / "packet.json").is_file()
    assert not (tmp_path / "folded" / "packet.md").exists()
    assert (tmp_path / "explicit" / "packet.md").is_file()
    assert json.loads(folded.stdout)["packet"] == str(tmp_path / "folded" / "packet.json")
    assert json.loads(explicit.stdout)["packet"] == str(tmp_path / "explicit" / "packet.md")
    envelope = json.loads(folded.stdout)
    assert envelope["format_version"] == FORMAT_VERSION
    assert envelope["out"] == str(tmp_path / "folded")
    assert envelope["features"] == str(tmp_path / "folded" / "features")


# ------------------------------------------------------------------- writing


def test_the_default_out_is_named_by_the_milestone_slug(tmp_path: Path) -> None:
    """``.absicht/build/packets/m1`` — the slug the id carries after its
    ``milestone:`` prefix, not the whole id and not the prefix's own spelling."""

    with _cwd(tmp_path / "cwd") as cwd:
        result = _packet()

        assert result.exit_code == ExitCode.OK
        assert (cwd / ".absicht" / "build" / "packets" / "m1" / "packet.md").is_file()
        assert not (cwd / ".absicht" / "build" / "packets" / "milestone:m1").exists()


def test_stdout_prints_the_body_byte_identical_and_writes_no_packet(tmp_path: Path) -> None:
    written = _body(tmp_path / "written")

    with _cwd(tmp_path / "cwd") as cwd:
        result = _packet("--out", str(tmp_path / "elsewhere"), "--stdout")

        assert result.exit_code == ExitCode.OK
        # Byte-identical to the file a write produces, newline included.
        assert result.stdout == written
        assert not (tmp_path / "elsewhere").exists()
        # Features are a real directory write even under --stdout: they land
        # relative to the cwd, which is the decision --help documents.
        assert (cwd / "features" / FEATURE).is_file()


def test_no_features_leaves_no_features_dir_and_no_note(tmp_path: Path) -> None:
    out = tmp_path / "packet"

    plain = _packet("--out", str(out), "--no-features")
    as_json = _packet("--out", str(tmp_path / "json"), "--no-features", "--json")

    assert plain.exit_code == ExitCode.OK
    assert as_json.exit_code == ExitCode.OK
    assert not (out / "features").exists()
    assert "features/" not in (out / "packet.md").read_text(encoding="utf-8")
    assert "features" not in json.loads(as_json.stdout)


def test_features_dir_names_where_they_land(tmp_path: Path) -> None:
    out = tmp_path / "packet"

    result = _packet("--out", str(out), "--features-dir", "gherkin")

    assert result.exit_code == ExitCode.OK
    assert (out / "gherkin" / FEATURE).is_file()
    assert not (out / "features").exists()
    # The done-when section points where the files actually are.
    assert "`gherkin/`" in (out / "packet.md").read_text(encoding="utf-8")


# -------------------------------------------------------------------- sealing


def _expected_digest(store: Path, *names: str) -> str:
    """The digest computed independently of the CLI: the store's own behaviors
    through the same renderer, folded by the same digest function."""
    index = Index(resolve(load_store(store)))
    rendered = {}
    for name in names:
        behavior = index.get(f"behavior:{name.removesuffix('.feature')}")
        assert isinstance(behavior, Behavior)
        rendered[name] = render_feature(behavior, index)
    return observations_digest(rendered)


def test_seal_writes_a_lock_matching_the_repo_and_the_rendered_features(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    _as_repo(store)

    sealed = _packet("--out", str(tmp_path / "sealed"), "--seal", store=store)
    result = _packet("--out", str(tmp_path / "body"), "--seal", "--format", "json", store=store)

    assert sealed.exit_code == ExitCode.OK
    assert result.exit_code == ExitCode.OK
    lock = json.loads((tmp_path / "sealed" / "packet.lock").read_text(encoding="utf-8"))
    assert set(lock) == {"format_version", "design_rev", "observations_digest"}
    assert lock["format_version"] == FORMAT_VERSION
    assert lock["design_rev"] == current_rev(store)
    assert lock["observations_digest"] == _expected_digest(store, FEATURE)
    # The body carries the rev the lock does, so the packet is self-describing
    # about the design it was sealed against.
    document = json.loads((tmp_path / "body" / "packet.json").read_text(encoding="utf-8"))
    assert document["design_rev"] == lock["design_rev"]


def test_stdout_with_seal_is_a_usage_error(tmp_path: Path) -> None:
    """A seal with nowhere durable to put ``packet.lock`` defeats its own
    purpose; an implicit fallback location would be a surprise, not a favour."""

    result = _packet("--out", str(tmp_path / "out"), "--stdout", "--seal")

    assert result.exit_code == ExitCode.USAGE
    assert "--seal" in result.stderr
    assert "--stdout" in result.stderr
    assert result.stdout == ""


def test_seal_with_no_features_is_a_usage_error(tmp_path: Path) -> None:
    """The digest seals the rendered scenarios; zero files is not a meaningful
    seal, and silently turning features back on would override an explicit
    flag."""

    result = _packet("--out", str(tmp_path / "out"), "--no-features", "--seal")

    assert result.exit_code == ExitCode.USAGE
    assert "--no-features" in result.stderr
    assert "--seal" in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "out").exists()


# ------------------------------------------------------------- broken calls


def test_an_unknown_milestone_is_a_usage_error(tmp_path: Path) -> None:
    result = _packet("--out", str(tmp_path / "out"), milestone="milestone:nope")

    assert result.exit_code == ExitCode.USAGE
    assert "milestone:nope" in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "out").exists()


def test_a_milestone_with_no_scope_is_findings(tmp_path: Path, scratch: Path) -> None:
    """The milestone exists but names nothing an agent may touch: a true
    statement about the design (exit 1), not a broken invocation (exit 2)."""

    result = _packet(
        "--out", str(tmp_path / "out"), store=_unscoped(scratch), milestone="milestone:unscoped"
    )

    assert result.exit_code == ExitCode.FINDINGS
    assert "says nothing about what may be touched" in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "out").exists()


def test_include_and_exclude_are_gone(tmp_path: Path) -> None:
    """A packet carries the milestone's own selection: a hand-narrowed one
    would verify against a slice nobody designed, so the flags that narrowed
    it are not quietly accepted and ignored — they are rejected."""

    for flag in ("--include", "--exclude"):
        result = _packet("--out", str(tmp_path / "out"), flag, "component:catalog")

        assert result.exit_code == ExitCode.USAGE
        assert flag in result.stderr


def test_a_negative_horizon_is_a_usage_error(tmp_path: Path) -> None:
    result = _packet("--out", str(tmp_path / "out"), "--horizon", "-1")

    assert result.exit_code == ExitCode.USAGE
    assert "--horizon" in result.stderr


# --------------------------------------------------------------- building at a rev


def test_a_packet_at_a_rev_reflects_that_revs_store(tmp_path: Path) -> None:
    """The store moves after its first commit; a packet at that commit folds
    the tree as it stood then — reached through the command's own ``--rev`` and
    through the root's, which must mean the same thing."""

    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    _as_repo(store)
    first = _git(store, "rev-parse", "HEAD").strip()
    _retitle_outcome(store, V2_OUTCOME)
    _git(store, "add", "-A")
    _git(store, "commit", "-qm", "c2")
    argv = ["--stdout", "--format", "json", "--no-features"]

    on_working_tree = _packet(*argv, store=store)
    at_rev = _packet(*argv, f"--rev={first}", store=store)
    from_root = runner.invoke(
        app, ["--store", str(store), "--rev", first, "packet", "milestone:m1", *argv]
    )

    assert on_working_tree.exit_code == ExitCode.OK
    assert at_rev.exit_code == ExitCode.OK
    assert from_root.exit_code == ExitCode.OK
    assert json.loads(on_working_tree.stdout)["outcome"] == V2_OUTCOME
    assert json.loads(at_rev.stdout)["outcome"] == V1_OUTCOME
    assert json.loads(from_root.stdout)["outcome"] == V1_OUTCOME


def test_seal_at_a_rev_stamps_that_revs_sha(tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    _as_repo(store)
    first = _git(store, "rev-parse", "HEAD").strip()
    _retitle_outcome(store, V2_OUTCOME)
    _git(store, "add", "-A")
    _git(store, "commit", "-qm", "c2")

    result = _packet("--out", str(tmp_path / "out"), "--seal", f"--rev={first}", store=store)

    assert result.exit_code == ExitCode.OK
    lock = json.loads((tmp_path / "out" / "packet.lock").read_text(encoding="utf-8"))
    assert lock["design_rev"] == resolve_rev(first, store)
    assert lock["design_rev"] != current_rev(store)


# ----------------------------------------------------------------- the run store


def test_issuance_is_recorded_beside_the_store(tmp_path: Path) -> None:
    """``ab packet`` records milestone, design rev, packet id, timestamp and
    target agent in the store's own ``build/runs.db``. The id is the digest of
    milestone plus design rev, so the unsealed and the sealed issuance of one
    milestone are two packets: they were built at two revs."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    _as_repo(store)
    rev = current_rev(store)

    plain = _packet("--out", str(tmp_path / "plain"), "--no-features", store=store)
    sealed = _packet(
        "--out", str(tmp_path / "sealed"), "--seal", "--target-agent", "agent/one", store=store
    )

    assert plain.exit_code == ExitCode.OK
    assert sealed.exit_code == ExitCode.OK
    by_id = {issued.packet_id: issued for issued in runstore.packets_for(store, "milestone:m1")}
    assert set(by_id) == {
        runstore.packet_id("milestone:m1", ""),
        runstore.packet_id("milestone:m1", rev),
    }
    assert by_id[runstore.packet_id("milestone:m1", "")] == runstore.IssuedPacket(
        packet_id=runstore.packet_id("milestone:m1", ""),
        milestone="milestone:m1",
        design_rev="",
        issued_at=by_id[runstore.packet_id("milestone:m1", "")].issued_at,
        target_agent=None,
    )
    assert by_id[runstore.packet_id("milestone:m1", rev)].design_rev == rev
    assert by_id[runstore.packet_id("milestone:m1", rev)].target_agent == "agent/one"
    # The timestamp is the CLI's clock, spelled ISO-8601 UTC.
    for issued in by_id.values():
        assert datetime.fromisoformat(issued.issued_at).utcoffset() == timedelta(0)


def test_reissuing_upserts_the_issuance_record(tmp_path: Path) -> None:
    """Regeneration is the normal case: re-issuing the same packet is the
    newest issuance of one packet, not a second row."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)

    first = _packet(
        "--out", str(tmp_path / "one"), "--no-features", "--target-agent", "agent/one", store=store
    )
    second = _packet(
        "--out", str(tmp_path / "two"), "--no-features", "--target-agent", "agent/two", store=store
    )

    assert first.exit_code == ExitCode.OK
    assert second.exit_code == ExitCode.OK
    (issued,) = runstore.packets_for(store, "milestone:m1")
    assert issued.packet_id == runstore.packet_id("milestone:m1", "")
    assert issued.target_agent == "agent/two"


def test_a_future_run_store_fails_the_command_before_it_writes(tmp_path: Path) -> None:
    """A ``runs.db`` left by a newer ``ab`` is refused rather than guessed at:
    the exit names the mismatch (4), the message names the file, and the
    packet is not half-delivered on top of it."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    db = store / "build" / "runs.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {runstore.USER_VERSION + 1}")
    conn.close()

    result = _packet("--out", str(tmp_path / "out"), "--no-features", store=store)

    assert result.exit_code == ExitCode.SCHEMA_MISMATCH
    assert "runs.db" in result.stderr
    assert not (tmp_path / "out").exists()


# ----------------------------------------------------------------- behaviors


def _guarded(store: Path) -> Path:
    """The clean fixture plus one active behavior watching the scope that the
    milestone does not include — the must-not-break side, which ``clean/``
    itself leaves empty, read off a store an author wrote."""
    (store / "behaviors" / "cancel-audited.md").write_text(
        "---\n"
        "id: behavior:cancel-audited\n"
        "title: Cancellations are audited\n"
        "state: specified\n"
        "trigger: Anything cancels an order.\n"
        "observations:\n"
        "- id: behavior:cancel-audited#obs-1\n"
        "  statement: No cancellation is audited twice.\n"
        "  at: component:cancellation\n"
        "  outcome: must_not\n"
        "---\n",
        encoding="utf-8",
    )
    return store


def test_the_behavior_lists_reach_the_command_output(scratch: Path) -> None:
    store = _guarded(scratch)

    result = _packet("--stdout", "--format", "json", "--no-features", store=store)

    assert result.exit_code == ExitCode.OK
    document = json.loads(result.stdout)
    assert document["satisfy"] == ["behavior:order-cancelled"]
    assert document["must_not_break"] == ["behavior:cancel-audited"]
    fidelities = {element["ref"]: element["fidelity"] for element in document["elements"]}
    assert fidelities["behavior:order-cancelled"] == "full"
    assert fidelities["behavior:cancel-audited"] == "full"
    # Watching nothing in scope is joining no list: the catalog behavior rides
    # in no ring the horizon finds from cancellation either.
    assert "behavior:catalog-browsable" not in fidelities


def test_the_md_document_carries_both_behavior_sections(scratch: Path) -> None:
    store = _guarded(scratch)

    result = _packet("--stdout", "--no-features", store=store)

    assert result.exit_code == ExitCode.OK
    document = result.stdout
    assert "## Behaviors to satisfy" in document
    assert "### Cancelling an unshipped order" in document
    assert (
        "- `behavior:order-cancelled#obs-1` — The order reads cancelled. "
        "(must, at component:orders)" in document
    )
    # The must-not-break section leads with the regression framing.
    not_break_at = document.index("## Behaviors that must not break")
    assert "Standing expectations" in document[not_break_at:]
    assert "regression" in document[not_break_at:]
    assert "### Cancellations are audited" in document[not_break_at:]
    assert (
        "- `behavior:cancel-audited#obs-1` — No cancellation is audited twice. "
        "(must_not, at component:cancellation)" in document[not_break_at:]
    )


def test_a_feature_file_lands_for_every_behavior_the_packet_lists(
    tmp_path: Path, scratch: Path
) -> None:
    """The ``.feature`` files cover both lists, named by the behavior's slug:
    the work an agent implements and the expectations it must not break are
    equally executable, and the names are what ``packet.lock`` seals."""
    store = _guarded(scratch)
    _as_repo(store)
    out = tmp_path / "packet"

    result = _packet("--out", str(out), "--seal", store=store)

    assert result.exit_code == ExitCode.OK
    assert {path.name for path in (out / "features").iterdir()} == {
        "order-cancelled.feature",
        "cancel-audited.feature",
    }
    lock = json.loads((out / "packet.lock").read_text(encoding="utf-8"))
    assert lock["observations_digest"] == _expected_digest(
        store, "order-cancelled.feature", "cancel-audited.feature"
    )


def test_the_same_store_assembles_a_byte_identical_artifact(tmp_path: Path, scratch: Path) -> None:
    """Regeneration replaces storage, so the same store re-packeted must land
    the same bytes — both formats, lists included."""
    store = _guarded(scratch)

    for name in ("one", "two"):
        for output_format in ("md", "json"):
            result = _packet(
                "--out",
                str(tmp_path / name),
                "--no-features",
                "--format",
                output_format,
                store=store,
            )
            assert result.exit_code == ExitCode.OK

    for artifact in ("packet.md", "packet.json"):
        assert (tmp_path / "one" / artifact).read_bytes() == (
            tmp_path / "two" / artifact
        ).read_bytes()
