"""``ab gaps``: everything unfinished, as an attributed worklist.

What these tests pin, per ``docs/tasks/23-gaps.md``:

- the four gap sources unioned into one entry per element, every reason
  spelled — an ``unknown`` with no owner says both, not just "unfinished"
  vaguely, because ``ab list --state unknown`` already answers the unannotated
  question (``brownfield/`` is the mix the fixture exists for);
- ``--overdue`` keeps only questions past ``due_on`` with no ``resolved_by``:
  the flag cannot mean anything for a non-question gap, and those are
  excluded, never an error;
- ``--blocking REF`` answers both edges that say "blocks" — a question's own
  ``blocks``, and a milestone's knowingly-open ``unresolved`` — and a REF
  naming nothing is ``USAGE``, the exit-code table's broken invocation;
- ``--kind`` and ``--owner`` filter the unioned set;
- ``clean/`` answers empty in both formats — the fixture is meant to be
  complete;
- ``--format json`` is the ``schema_version`` envelope of
  ``00-conventions.md`` carrying the operative dates, and ``--json`` folds
  into a default ``--format`` without overriding an explicit one
  (docs/adr/0001).

A non-empty worklist still exits ``OK``: a worklist is the answer, not a
finding about the design — that judgement is ``ab check``'s, and every test
below asserts the exit code against ``brownfield/``, which is never empty.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.models import SCHEMA_VERSION

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "systems"
BROWNFIELD = FIXTURES / "brownfield"
CLEAN = FIXTURES / "clean"


def _gaps(store: Path, *flags: str) -> Any:
    return runner.invoke(app, ["--store", str(store), "gaps", *flags])


def _document(store: Path, *flags: str) -> dict[str, Any]:
    """The ``--format json`` answer, with schema version and exit code asserted
    once here rather than in every test below."""
    result = _gaps(store, "--format", "json", *flags)
    assert result.exit_code == ExitCode.OK
    document = json.loads(result.stdout)
    assert document["schema_version"] == SCHEMA_VERSION
    return document


def _reasons(store: Path, *flags: str) -> dict[str, list[str]]:
    """The worklist as ``ref → reasons``, the shape every attribution test
    reads; anything else a gap entry carries has its own test."""
    return {gap["ref"]: gap["reasons"] for gap in _document(store, *flags)["gaps"]}


def test_brownfield_mix_attributes_every_reason() -> None:
    """One entry per unfinished element with the reasons spelled exactly: the
    observed legacy elements are unfinished *and* unowned, the well-formed
    questions carry their own reason — overdue or not — instead of drowning in
    `unowned`, the owned milestone is on the list for its state alone, and the
    expired external is the one single-reason entry: its state is fine, its
    trust lapsed."""
    assert _reasons(BROWNFIELD) == {
        "component:legacy-billing": ["state=observed", "unowned"],
        "component:shadow-report": ["state=observed", "unowned"],
        "data:audit-log": ["state=observed", "unowned"],
        "external:payment-api": ["external-expired"],
        "milestone:reconcile-mvp": ["state=unknown"],
        "question:nightly-retry": ["state=unknown", "question-overdue"],
        "question:refund-window": ["state=unknown", "question-open"],
        "requirement:audit-trail": ["state=unknown", "unowned"],
        "story:reconcile-billing": ["state=observed", "unowned"],
        "system:legacy": ["state=observed", "unowned"],
    }


def test_the_worklist_is_in_id_order_and_carries_the_operative_dates() -> None:
    """Id order, the deterministic default `ab list` set and no sort flag
    changes here; and the dates each dated reason hangs on, so a consumer can
    prioritize without re-reading the element."""
    document = _document(BROWNFIELD)

    refs = [gap["ref"] for gap in document["gaps"]]
    assert refs == sorted(refs)
    by_ref = {gap["ref"]: gap for gap in document["gaps"]}
    assert by_ref["question:nightly-retry"]["due_on"] == "2026-01-10"
    assert by_ref["question:refund-window"]["due_on"] == "2099-01-01"
    assert by_ref["external:payment-api"]["expires_on"] == "2026-01-01"
    # Undated gaps carry None, not a fabricated or copied-over date.
    assert by_ref["requirement:audit-trail"]["due_on"] is None
    assert by_ref["requirement:audit-trail"]["expires_on"] is None
    # The element itself rides along: the entry annotates it, it does not
    # replace it.
    assert by_ref["requirement:audit-trail"]["element"]["state"] == "unknown"


def test_overdue_keeps_only_open_questions_past_their_due_date() -> None:
    """`question:nightly-retry` is past its due date and unresolved;
    `question:refund-window` is not due for decades, and no non-question gap
    has a due date at all — `--overdue` excludes both rather than erroring."""
    assert _reasons(BROWNFIELD, "--overdue") == {
        "question:nightly-retry": ["state=unknown", "question-overdue"],
    }


def test_blocking_answers_both_edges_that_say_blocks() -> None:
    """`question:nightly-retry` names the milestone in its own `blocks`;
    `milestone:reconcile-mvp` knowingly leaves `question:refund-window` open
    in `unresolved`. Both are gaps blocking the milestone — the two halves of
    the flag, through one ref."""
    assert _reasons(BROWNFIELD, "--blocking", "milestone:reconcile-mvp") == {
        "question:nightly-retry": ["state=unknown", "question-overdue"],
        "question:refund-window": ["state=unknown", "question-open"],
    }
    # An element ref: only the question whose own `blocks` names it. A gap
    # with no `blocks` field of its own — the unowned requirement — is not
    # blocking anything, whatever else points at the story.
    assert _reasons(BROWNFIELD, "--blocking", "story:reconcile-billing") == {
        "question:refund-window": ["state=unknown", "question-open"],
    }


def test_a_blocking_ref_that_names_nothing_is_a_usage_error() -> None:
    """Same policy as `show` and `list --milestone`: an empty answer would read
    as "nothing blocks it", which is a different claim than "no such element"."""
    result = _gaps(BROWNFIELD, "--blocking", "milestone:never")

    assert result.exit_code == ExitCode.USAGE
    assert "--blocking" in result.stderr
    assert result.stdout == ""


def test_kind_and_owner_filter_the_unioned_set() -> None:
    assert set(_reasons(BROWNFIELD, "--kind", "question")) == {
        "question:nightly-retry",
        "question:refund-window",
    }
    # Only the question owned by finance survives; the ownerless majority of
    # the worklist does not — an ignored flag would answer with all of it.
    assert set(_reasons(BROWNFIELD, "--owner", "finance")) == {"question:nightly-retry"}


def test_clean_answers_empty_in_both_formats() -> None:
    """`clean/` is complete: no entry, nothing at all on stdout in text (no
    blank line where a row would be), and the json envelope still envelopes
    an empty list — the shape is the contract even when the answer is "done"."""
    result = _gaps(CLEAN)

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""
    assert _document(CLEAN)["gaps"] == []


def test_text_is_one_aligned_line_per_gap() -> None:
    """The worklist a human reads: id, every reason with its operative date,
    then the title — aligned like `ab list`'s text format."""
    result = _gaps(BROWNFIELD, "--kind", "question")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "question:nightly-retry  state=unknown, question-overdue (due 2026-01-10)"
        "  Why does the nightly job retry three times?",
        "question:refund-window  state=unknown, question-open (due 2099-01-01)"
        "  How long is the refund window?",
    ]


def test_json_folds_into_a_default_format_only() -> None:
    folded = _gaps(BROWNFIELD, "--json")
    explicit = _gaps(BROWNFIELD, "--format", "text", "--json")

    assert folded.exit_code == ExitCode.OK
    assert json.loads(folded.stdout)["schema_version"] == SCHEMA_VERSION
    assert explicit.stdout.startswith("component:legacy-billing")
