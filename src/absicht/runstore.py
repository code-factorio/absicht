"""Run history — packets issued, verification runs — in SQLite, not in git.

Addendum §8 (docs/spec/ABSICHT-MODEL-ADDENDUM.md#8): packets and verification
runs are machine-generated, appended per run and never reviewed as a diff, so
they do not belong in the repository. A local store beside the design store
records two things, and losing it loses run history, not design — a packet
artifact is deterministic from milestone plus design rev and is regenerated,
and a verification run can be re-run.

The store is ``build/runs.db`` under the store root (pinned in
docs/tasks/50-addendum-conventions.md): inside the already-gitignored build
directory, destroyed by exactly the actions that destroy the other derived
artifacts.

Two tables, matching §8's tuples:

- ``packets`` — one row per packet id ever issued: the milestone, the design
  rev it was built at, when, and to whom. The artifact itself is never
  stored; it is regenerated.
- ``runs`` — one row per criterion/observation result of one verification
  run. A run has no header table: its rows share
  ``(packet_id, commit_sha, recorded_at)`` and are written in one
  transaction, so a failing row rolls the whole run back — and a run with no
  results leaves no trace. ``result`` is text, not an enum or a foreign key:
  59's vocabulary (``checked`` / ``no_check`` / ``advisory``) plus whatever
  verify's rules record, additive like the JSON envelope.

Packet ids are ``pkt-`` plus the first 12 hex of
``sha256(milestone + design_rev)`` — an opaque handle pinned here so that
re-issuing the same packet is the same id and history groups naturally. The
artifact's deterministic *content* is ``absicht.packet``'s business; only the
id is this module's.

Timestamps are ISO-8601 UTC strings supplied by the caller, never read from
a clock in here — the module stays deterministic and testable for the same
reason ``check`` takes ``today`` as a parameter. The CLI is the one spelling
of them, so the TEXT columns order lexicographically as timestamps.

The schema is versioned with ``PRAGMA user_version``. Version 0 is an absent
schema (a fresh or empty file): reads answer empty and the next write creates
it. A version newer than this module knows raises ``RunStoreError`` rather
than being guessed at — a store from a future ab is history this one must
neither corrupt nor silently drop.

The API never hands out a connection or a cursor: plain frozen records in,
plain frozen records out.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

USER_VERSION = 1
"""The schema version this module writes and understands."""

RUNS_DB = Path("build") / "runs.db"
"""Where the store sits under the store root."""


class RunStoreError(Exception):
    """The store on disk is not one this module may safely use."""


@dataclass(frozen=True, slots=True)
class IssuedPacket:
    """One packet ever issued — a row of ``packets``."""

    packet_id: str
    milestone: str
    design_rev: str
    issued_at: str
    target_agent: str | None


@dataclass(frozen=True, slots=True)
class RunResult:
    """One criterion/observation result — a row of ``runs``."""

    criterion: str
    result: str
    evidence_ref: str | None


@dataclass(frozen=True, slots=True)
class Run:
    """One verification run: the header its rows share, plus the rows."""

    packet_id: str
    commit_sha: str
    recorded_at: str
    results: tuple[RunResult, ...]


# The stamp at the end is USER_VERSION spelled as a literal: a PRAGMA binds
# no parameters, so the two are neighbours or they drift.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS packets (
    packet_id    TEXT PRIMARY KEY,
    milestone    TEXT NOT NULL,
    design_rev   TEXT NOT NULL,
    issued_at    TEXT NOT NULL,
    target_agent TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    packet_id    TEXT NOT NULL,
    commit_sha   TEXT NOT NULL,
    criterion    TEXT NOT NULL,
    result       TEXT NOT NULL,
    evidence_ref TEXT,
    recorded_at  TEXT NOT NULL
);
PRAGMA user_version = 1;
"""


def packet_id(milestone: str, design_rev: str) -> str:
    """The opaque handle of the packet built from ``milestone`` at ``design_rev``.

    Deterministic, so re-issuing is the same id and history groups naturally;
    opaque, because the artifact's deterministic content is the packet
    module's to derive and this handle only has to name it.
    """
    digest = hashlib.sha256(f"{milestone}{design_rev}".encode()).hexdigest()
    return f"pkt-{digest[:12]}"


def record_packet(
    root: Path,
    *,
    packet_id: str,
    milestone: str,
    design_rev: str,
    issued_at: str,
    target_agent: str | None,
) -> None:
    """Record (or re-record) a packet issuance, creating the store if needed.

    Upsert keyed by the packet id: regeneration is the normal case, and the
    newest issuance is the truth about when and to whom. Milestone and design
    rev are never updated — the id is derived from them, so for one id they
    cannot change.
    """
    conn = _open_for_write(root)
    try:
        with conn:
            conn.execute(
                "INSERT INTO packets (packet_id, milestone, design_rev, issued_at, target_agent) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (packet_id) DO UPDATE SET "
                "issued_at = excluded.issued_at, target_agent = excluded.target_agent",
                (packet_id, milestone, design_rev, issued_at, target_agent),
            )
    finally:
        conn.close()


def record_run(
    root: Path,
    *,
    packet_id: str,
    commit_sha: str,
    recorded_at: str,
    results: Sequence[RunResult],
) -> None:
    """Record one verification run — all of its rows, or none of them.

    The header ``(packet_id, commit_sha, recorded_at)`` rides on every row,
    and the batch shares one transaction: a row the schema refuses rolls the
    run back whole, which is the trace of a run there is no half-version of.
    A run with no results writes nothing (the schema has no header table).
    """
    conn = _open_for_write(root)
    try:
        with conn:
            conn.executemany(
                "INSERT INTO runs (packet_id, commit_sha, criterion, result, evidence_ref, "
                "recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (packet_id, commit_sha, r.criterion, r.result, r.evidence_ref, recorded_at)
                    for r in results
                ],
            )
    finally:
        conn.close()


def packets_for(root: Path, milestone: str) -> tuple[IssuedPacket, ...]:
    """Every packet ever issued for ``milestone``, oldest issuance first."""
    conn = _open_for_read(root)
    if conn is None:
        return ()
    try:
        rows = conn.execute(
            "SELECT packet_id, design_rev, issued_at, target_agent FROM packets "
            "WHERE milestone = ? ORDER BY issued_at, packet_id",
            (milestone,),
        ).fetchall()
    finally:
        conn.close()
    return tuple(
        IssuedPacket(
            packet_id=pid, milestone=milestone, design_rev=rev, issued_at=at, target_agent=agent
        )
        for pid, rev, at, agent in rows
    )


def runs_for(root: Path, packet_id: str) -> tuple[Run, ...]:
    """Every verification run recorded for ``packet_id``, oldest first.

    One ``Run`` per ``(commit_sha, recorded_at)`` header, its rows in the
    order they were written."""
    conn = _open_for_read(root)
    if conn is None:
        return ()
    try:
        rows = conn.execute(
            "SELECT commit_sha, recorded_at, criterion, result, evidence_ref FROM runs "
            "WHERE packet_id = ? ORDER BY recorded_at, commit_sha, rowid",
            (packet_id,),
        ).fetchall()
    finally:
        conn.close()
    grouped: dict[tuple[str, str], list[RunResult]] = {}
    for commit_sha, recorded_at, criterion, result, evidence_ref in rows:
        grouped.setdefault((commit_sha, recorded_at), []).append(
            RunResult(criterion=criterion, result=result, evidence_ref=evidence_ref)
        )
    return tuple(
        Run(
            packet_id=packet_id,
            commit_sha=commit_sha,
            recorded_at=recorded_at,
            results=tuple(results),
        )
        for (commit_sha, recorded_at), results in grouped.items()
    )


def latest_run(root: Path, packet_id: str) -> Run | None:
    """The most recent verification run for ``packet_id``, or ``None``."""
    runs = runs_for(root, packet_id)
    return runs[-1] if runs else None


def _open_for_read(root: Path) -> sqlite3.Connection | None:
    """A connection to the store under ``root``, or ``None`` when there is none.

    Absence is a valid state — a fresh clone has no history — so it answers
    ``None`` rather than raising, and never creates the file it looked for.
    A version-0 file (present but never stamped) is treated the same: no
    schema was written, so there is no history in it.
    """
    db = root / RUNS_DB
    if not db.is_file():
        return None
    conn = sqlite3.connect(db)
    version = _version(conn, db)
    if version == 0:
        conn.close()
        return None
    return conn


def _open_for_write(root: Path) -> sqlite3.Connection:
    """A connection that may create the store: parent dirs, schema, version —
    the only writer-side setup there is. Refuses a future version's file
    untouched rather than stamping this one's over it."""
    db = root / RUNS_DB
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    version = _version(conn, db)
    if version == 0:
        conn.executescript(_SCHEMA)
        return conn
    return conn


def _version(conn: sqlite3.Connection, db: Path) -> int:
    """The store's ``user_version``, raising on one from a future ``ab``."""
    row = conn.execute("PRAGMA user_version").fetchone()
    version = int(row[0]) if row else 0
    if version > USER_VERSION:
        conn.close()
        raise RunStoreError(
            f"{db} is run-store schema version {version}, newer than the "
            f"{USER_VERSION} this ab understands. It holds run history, not design: "
            "remove it and the history starts over."
        )
    return version
