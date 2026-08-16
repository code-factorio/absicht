"""``absicht.runstore``: the local history of packets issued and runs verified.

``docs/tasks/58-run-store.md``'s contract, pinned against the module rather
than through a command: what lands under a store's ``build/runs.db`` when
``ab packet`` issues and ``ab verify`` records, and the properties that make
the store boring enough to trust —

- both tables round-trip through the plain records callers get back, never a
  cursor;
- a run is written whole or not at all: its rows share one transaction;
- a missing store is a valid state (a fresh clone has no history): reads
  answer empty, and the first write creates the db and its parent dirs;
- re-recording a packet id upserts — regeneration is the normal case, not a
  duplicate row;
- the schema is stamped with ``PRAGMA user_version``, and a version from a
  future ``ab`` is refused loudly rather than guessed at;
- the packet id is the pinned digest: ``pkt-`` plus the first 12 hex of
  sha256(milestone + design_rev).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

import pytest

from absicht import runstore
from absicht.runstore import (
    IssuedPacket,
    Run,
    RunResult,
    latest_run,
    packet_id,
    packets_for,
    record_packet,
    record_run,
    runs_for,
)

RUNS_DB = Path("build") / "runs.db"

# Fixed instants, never a clock: the module's determinism is the point, and
# the ordering assertions need timestamps that do not depend on test runtime.
AT_ONE = "2026-08-16T10:00:00+00:00"
AT_TWO = "2026-08-16T11:30:00+00:00"

DESIGN_REV = "a" * 40
MILESTONE = "milestone:m1"


def _issue(root: Path, *, issued_at: str = AT_ONE, agent: str | None = None) -> str:
    """Record one issuance and hand back the packet id it was recorded under."""
    pid = packet_id(MILESTONE, DESIGN_REV)
    record_packet(
        root,
        packet_id=pid,
        milestone=MILESTONE,
        design_rev=DESIGN_REV,
        issued_at=issued_at,
        target_agent=agent,
    )
    return pid


def _stamped(root: Path) -> int:
    """The store's ``user_version``, read the way nothing else in the codebase does."""
    conn = sqlite3.connect(root / RUNS_DB)
    try:
        row = conn.execute("PRAGMA user_version").fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else 0


def _stamp_future_version(root: Path, version: int) -> None:
    """A db as a newer ``ab`` would have left it: same file, a ``user_version``
    this one never writes."""
    db = root / RUNS_DB
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {version}")
    conn.close()


# ---------------------------------------------------------------- round trips


def test_an_issued_packet_round_trips(tmp_path: Path) -> None:
    pid = _issue(tmp_path, agent="agent/one")

    issued = packets_for(tmp_path, MILESTONE)

    assert issued == (
        IssuedPacket(
            packet_id=pid,
            milestone=MILESTONE,
            design_rev=DESIGN_REV,
            issued_at=AT_ONE,
            target_agent="agent/one",
        ),
    )
    assert packets_for(tmp_path, "milestone:other") == ()


def test_runs_round_trip_grouped_by_their_header(tmp_path: Path) -> None:
    pid = _issue(tmp_path)
    first = (
        RunResult(criterion="story:cancel-order#ac-1", result="checked", evidence_ref="tests/a.py"),
        RunResult(criterion="story:cancel-order#ac-2", result="no_check", evidence_ref=None),
    )
    second = (RunResult(criterion="story:cancel-order#ac-1", result="no_check", evidence_ref=None),)
    record_run(tmp_path, packet_id=pid, commit_sha="f" * 40, recorded_at=AT_ONE, results=first)
    record_run(tmp_path, packet_id=pid, commit_sha="0" * 40, recorded_at=AT_TWO, results=second)

    runs = runs_for(tmp_path, pid)

    assert runs == (
        Run(packet_id=pid, commit_sha="f" * 40, recorded_at=AT_ONE, results=first),
        Run(packet_id=pid, commit_sha="0" * 40, recorded_at=AT_TWO, results=second),
    )
    assert runs_for(tmp_path, "pkt-never-issued") == ()
    assert latest_run(tmp_path, pid) == runs[1]
    assert latest_run(tmp_path, "pkt-never-issued") is None


# ------------------------------------------------------------------- absence


def test_reads_against_a_missing_store_answer_empty(tmp_path: Path) -> None:
    """A fresh clone has no history, which is a valid state rather than an
    error — and a read must not conjure the file it looked for."""
    assert packets_for(tmp_path, MILESTONE) == ()
    assert runs_for(tmp_path, "pkt-x") == ()
    assert latest_run(tmp_path, "pkt-x") is None
    assert not (tmp_path / RUNS_DB).exists()


def test_the_first_write_creates_the_db_and_its_parents(tmp_path: Path) -> None:
    root = tmp_path / "deep" / "store"

    _issue(root)

    assert (root / RUNS_DB).is_file()


def test_an_empty_db_file_is_still_no_history(tmp_path: Path) -> None:
    """Version 0 means no schema was ever written (an empty file, say): reads
    treat it like absence, and the next write stamps it."""
    db = tmp_path / RUNS_DB
    db.parent.mkdir(parents=True)
    db.touch()

    assert packets_for(tmp_path, MILESTONE) == ()
    assert latest_run(tmp_path, "pkt-x") is None

    _issue(tmp_path)

    assert _stamped(tmp_path) == runstore.USER_VERSION
    assert len(packets_for(tmp_path, MILESTONE)) == 1


# ------------------------------------------------------------------ upserting


def test_re_recording_a_packet_id_upserts(tmp_path: Path) -> None:
    """Regeneration is the normal case: re-issuing the same packet id is the
    newest issuance of one packet, not a second row."""
    _issue(tmp_path, issued_at=AT_ONE, agent="agent/one")
    _issue(tmp_path, issued_at=AT_TWO, agent="agent/two")

    (issued,) = packets_for(tmp_path, MILESTONE)

    assert issued.issued_at == AT_TWO
    assert issued.target_agent == "agent/two"


# ---------------------------------------------------------------- transactions


def test_a_run_is_written_whole_or_not_at_all(tmp_path: Path) -> None:
    pid = _issue(tmp_path)
    kept = (RunResult(criterion="story:cancel-order#ac-1", result="checked", evidence_ref="a.py"),)
    record_run(tmp_path, packet_id=pid, commit_sha="f" * 40, recorded_at=AT_ONE, results=kept)

    with pytest.raises(sqlite3.IntegrityError):
        record_run(
            tmp_path,
            packet_id=pid,
            commit_sha="0" * 40,
            recorded_at=AT_TWO,
            results=(
                RunResult(
                    criterion="story:cancel-order#ac-2", result="checked", evidence_ref="b.py"
                ),
                # The fault that rolls the run back: a NULL criterion, refused
                # by the column's NOT NULL — any per-row constraint failure.
                RunResult(criterion=None, result="checked", evidence_ref="c.py"),
            ),
        )

    assert runs_for(tmp_path, pid) == (
        Run(packet_id=pid, commit_sha="f" * 40, recorded_at=AT_ONE, results=kept),
    )


# ----------------------------------------------------------------- versioning


def test_the_schema_version_is_stamped_on_creation(tmp_path: Path) -> None:
    _issue(tmp_path)

    assert _stamped(tmp_path) == runstore.USER_VERSION


def test_a_future_version_is_refused_on_read(tmp_path: Path) -> None:
    future = runstore.USER_VERSION + 1
    _stamp_future_version(tmp_path, future)

    with pytest.raises(runstore.RunStoreError) as refused:
        packets_for(tmp_path, MILESTONE)

    # Loud means actionable: the file, the version found, the one understood.
    assert str(tmp_path / RUNS_DB) in str(refused.value)
    assert str(future) in str(refused.value)
    with pytest.raises(runstore.RunStoreError):
        runs_for(tmp_path, "pkt-x")
    with pytest.raises(runstore.RunStoreError):
        latest_run(tmp_path, "pkt-x")


def test_a_future_version_is_refused_on_write_and_left_alone(tmp_path: Path) -> None:
    future = runstore.USER_VERSION + 1
    _stamp_future_version(tmp_path, future)

    with pytest.raises(runstore.RunStoreError):
        _issue(tmp_path)
    with pytest.raises(runstore.RunStoreError):
        record_run(tmp_path, packet_id="pkt-x", commit_sha="f" * 40, recorded_at=AT_ONE, results=())

    # Refused means refused: this ab neither downgrades nor writes into it.
    assert _stamped(tmp_path) == future


# ---------------------------------------------------------------------- the id


def test_the_packet_id_is_the_pinned_digest() -> None:
    expected = "pkt-" + hashlib.sha256(MILESTONE.encode() + DESIGN_REV.encode()).hexdigest()[:12]

    assert packet_id(MILESTONE, DESIGN_REV) == expected
    # Re-issuing the same packet at the same rev is the same handle.
    assert packet_id(MILESTONE, DESIGN_REV) == expected
    assert packet_id(MILESTONE, "b" * 40) != expected
    assert packet_id("milestone:m2", DESIGN_REV) != expected
    assert re.fullmatch(r"pkt-[0-9a-f]{12}", expected)
