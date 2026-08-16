# 58 — The run store: packets issued, verification runs

## Depends on
[00-conventions.md](00-conventions.md),
[50-addendum-conventions.md](50-addendum-conventions.md). Independent of the
other 5x tasks — it can be built in parallel with 51–57; only its *callers*
([57](57-packet-behaviors.md), [59](59-verify-observations.md)) need it
landed.

## Goal

The place run history lives, per addendum §8: not in git. A small, boring
SQLite module with an API narrow enough that "what would we ever query"
stays answerable.

## Spec

> **Not in git.** They are machine-generated, produced per run, appended
> rather than authored, and never reviewed as a diff. […] A local store
> beside the design store records two things:
>
> - **Packet issued** — `(milestone, design rev, packet id, timestamp,
>   target agent)`. The packet artifact itself is deterministic from
>   milestone plus design rev, so it is regenerated rather than stored.
> - **Verification run** — `(packet id, commit sha, per-criterion result,
>   evidence ref)`.
>
> Losing this store loses run history, not design.
>
> — [addendum §8](../spec/ABSICHT-MODEL-ADDENDUM.md#8-where-packets-and-verification-runs-live)

## What to build

`src/absicht/runstore.py` — stdlib `sqlite3`, no new dependency:

- Location pinned in `50-addendum-conventions.md`:
  `.absicht/build/runs.db`, created on first write, parent dirs included.
  Reads against a missing store return empty, never raise — absence means
  "no history", which is a valid state (fresh clone).
- Schema, versioned with a `PRAGMA user_version` and matching §8's tuples:
  - `packets(packet_id TEXT PRIMARY KEY, milestone TEXT, design_rev TEXT,
    issued_at TEXT, target_agent TEXT)` — `issued_at` ISO-8601 UTC,
    supplied by the caller (the CLI layer), never read from a clock in
    this module: keeps the module deterministic and testable, same reason
    `check` takes `today` as a parameter.
  - `runs(packet_id TEXT, commit_sha TEXT, criterion TEXT, result TEXT,
    evidence_ref TEXT, recorded_at TEXT)` — one row per criterion/
    observation result; `result` values are [59](59-verify-observations.md)'s
    vocabulary (`checked` / `no_check` / `advisory`) plus whatever the
    existing verify rules record, stored as text, not an enum FK —
    additive, like the JSON envelope.
- API: `record_packet(...)`, `record_run(...)` (a run is one
  `(packet_id, commit_sha, recorded_at)` plus its per-criterion rows,
  written in one transaction), `packets_for(milestone)`,
  `runs_for(packet_id)`, `latest_run(packet_id)`. Return plain frozen
  dataclasses or pydantic records — callers never see a cursor.
- Packet id generation: deterministic content is the artifact's job; the
  *id* is an opaque handle — pin `pkt-` + first 12 hex of
  sha256(milestone + design_rev), so re-issuing the same packet is the
  same id and history groups naturally. Write it down in the module
  docstring.
- Wire the callers that already exist when this lands: `ab packet` records
  issuance (`--target-agent WHO` optional new flag, additive to
  `cli.md` — document it there in this task); `ab verify` records its run
  ([59](59-verify-observations.md) finishes this if verify lands later).

## Out of scope

- Any CLI for browsing history (`ab runs`?) — nothing in the spec asks for
  it yet; YAGNI until a consumer exists.
- Re-deriving lost history — §8 says re-run, not restore.

## Tests

- Round-trip both tables; one-transaction run writes (a failing row rolls
  back the run header).
- Missing db file: reads answer empty, first write creates.
- Re-recording the same packet id upserts rather than duplicating
  (regeneration is the normal case).
- `user_version` stamped; opening a future version fails loudly rather
  than guessing.

## Definition of done

- `absicht.runstore` in the import-linter layers list, same commit.
- `./scripts/verify.sh` clean.
