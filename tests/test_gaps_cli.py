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

Since the model addendum: a behavior with no observations joins the worklist
— the query-side twin of ``policy/behavior-needs-observations``, the way
unowned elements appear both places — and §7's owner inheritance annotates
an unowned ``unknown`` with the owner of the single element referencing it,
marked ``inherited``, never stored.

A non-empty worklist still exits ``OK``: a worklist is the answer, not a
finding about the design — that judgement is ``ab check``'s, and every test
below asserts the exit code against ``brownfield/``, which is never empty.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
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
        "behavior:reconciliation-fires": ["state=observed", "unowned"],
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
    assert explicit.stdout.startswith("behavior:reconciliation-fires")


# --- the addendum's additions ----------------------------------------------------


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def unobserved(tmp_path: Path) -> Path:
    """The zero-observation behavior beside an observed one, in the smallest
    store that holds the pair: `broken/` has the case but cannot reach a
    query (its parse failures are `build`'s refusal), and growing a shared
    fixture would move other tickets' exact-match worklist assertions."""
    root = tmp_path / "unobserved"
    _write(root, "system.yaml", "id: system:probe\ntitle: Probe\nstate: specified\nowner: root\n")
    _write(
        root,
        "components/probe.md",
        "---\nid: component:probe\ntitle: Probe\nstate: specified\nowner: root\n---\n",
    )
    _write(
        root,
        "behaviors/bare.md",
        "---\nid: behavior:bare\ntitle: Bare\nstate: specified\ntrigger: Something happens.\n---\n",
    )
    _write(
        root,
        "behaviors/watched.md",
        "---\nid: behavior:watched\ntitle: Watched\nstate: observed\nowner: root\n"
        "trigger: Something else happens.\nobservations:\n"
        "- id: behavior:watched#obs-1\n  statement: The probe saw it\n"
        "  at: component:probe\n  outcome: must\n---\n",
    )
    return root


def test_a_behavior_with_no_observations_is_a_gap_line(unobserved: Path) -> None:
    """The policy rule's query-side twin: the expectation with nothing
    observable is unfinished whatever its state — `behavior:bare` is
    `specified` and still lands on the worklist, for that reason alone.
    Its sibling stays on the list for its `observed` state and nothing else,
    which is what pins the reason to the zero, not to the kind."""
    assert _reasons(unobserved) == {
        "behavior:bare": ["no-observations"],
        "behavior:watched": ["state=observed"],
    }


# --- §7 owner inheritance --------------------------------------------------------


@pytest.fixture
def inheritance(tmp_path: Path) -> Path:
    """§7 in full, one file per case: `requirement:spike` inherits from the
    single referencing element that carries an owner;
    `requirement:self-owned` has an owner of its own; `component:contested`
    is referenced by two owners; and `component:deep` is referenced only by
    an ownerless unknown that itself inherits — the one-level bound. No
    fixture carries owners on referencing elements; the case gets a store of
    its own rather than moving other tickets' exact-match assertions."""
    root = tmp_path / "inheritance"
    _write(root, "system.yaml", "id: system:inheritance\ntitle: Inheritance\nstate: specified\n")
    _write(root, "requirements/spike.md", "---\nid: requirement:spike\ntitle: Spike it\n---\n")
    _write(
        root,
        "stories/spike-carrier.md",
        "---\nid: story:spike-carrier\ntitle: Spike carrier\nstate: specified\nowner: platform\n"
        "satisfies:\n- requirement:spike\n---\n",
    )
    _write(
        root,
        "requirements/self-owned.md",
        "---\nid: requirement:self-owned\ntitle: Self owned\nowner: qa\n---\n",
    )
    _write(
        root,
        "stories/qa-carrier.md",
        "---\nid: story:qa-carrier\ntitle: Qa carrier\nstate: specified\nowner: platform\n"
        "satisfies:\n- requirement:self-owned\n---\n",
    )
    _write(root, "components/contested.md", "---\nid: component:contested\ntitle: Contested\n---\n")
    _write(
        root,
        "requirements/by-a.md",
        "---\nid: requirement:by-a\ntitle: By A\nstate: specified\nowner: team-a\nrealized_by:\n"
        "- component:contested\n---\n",
    )
    _write(
        root,
        "requirements/by-b.md",
        "---\nid: requirement:by-b\ntitle: By B\nstate: specified\nowner: team-b\nrealized_by:\n"
        "- component:contested\n---\n",
    )
    _write(root, "components/deep.md", "---\nid: component:deep\ntitle: Deep\n---\n")
    _write(
        root,
        "requirements/mid.md",
        "---\nid: requirement:mid\ntitle: Mid\nrealized_by:\n- component:deep\n---\n",
    )
    _write(
        root,
        "stories/top.md",
        "---\nid: story:top\ntitle: Top\nstate: specified\nowner: platform\nsatisfies:\n"
        "- requirement:mid\n---\n",
    )
    return root


def _entries(store: Path, *flags: str) -> dict[str, dict[str, Any]]:
    """The worklist as ref → entry, for the tests that read past `reasons`."""
    return {gap["ref"]: gap for gap in _document(store, *flags)["gaps"]}


def test_an_unowned_unknown_reports_its_single_referencing_owner(
    inheritance: Path,
) -> None:
    """§7's inheritance: `requirement:spike` has no owner of its own and
    exactly one referencing element that does — it answers to platform,
    marked inherited in its own field, and stops being called unowned."""
    entries = _entries(inheritance)

    assert entries["requirement:spike"]["owner_inherited"] == "platform"
    assert entries["requirement:spike"]["reasons"] == ["state=unknown"]
    # An authored owner always stands: qa keeps the entry, inheritance or not.
    assert entries["requirement:self-owned"]["owner_inherited"] is None
    assert entries["requirement:self-owned"]["reasons"] == ["state=unknown"]


def test_two_referencing_owners_inherit_nothing(inheritance: Path) -> None:
    """Ambiguity is not a guess: `component:contested` is referenced by an
    owner and another owner, so no owner is reported and the element stays
    unowned on the worklist."""
    entries = _entries(inheritance)

    assert entries["component:contested"]["owner_inherited"] is None
    assert entries["component:contested"]["reasons"] == ["state=unknown", "unowned"]


def test_inheritance_goes_one_level_no_deeper(inheritance: Path) -> None:
    """`requirement:mid` inherits platform from `story:top`; the
    `component:deep` it references inherits nothing — mid's own `owner` is
    empty, and the owner mid itself inherited is never chained on."""
    entries = _entries(inheritance)

    assert entries["requirement:mid"]["owner_inherited"] == "platform"
    assert entries["component:deep"]["owner_inherited"] is None
    assert entries["component:deep"]["reasons"] == ["state=unknown", "unowned"]


def test_the_text_line_marks_the_inherited_owner(inheritance: Path) -> None:
    """The human-readable surface says whose it is and how it came to be
    known: `owner: platform (inherited)`, between the reasons and the title.
    The row is found by prefix rather than spelled whole, so the pin is the
    annotation and its place, not the id-column padding."""
    result = _gaps(inheritance, "--kind", "requirement")

    assert result.exit_code == ExitCode.OK
    spike = next(
        line for line in result.stdout.splitlines() if line.startswith("requirement:spike")
    )
    assert spike.endswith("state=unknown  owner: platform (inherited)  Spike it")


def test_owner_filters_by_the_inherited_owner_too(inheritance: Path) -> None:
    """`--owner platform` answers with both of platform's unknowns: the one
    it owns outright and the one it owns by §7's inheritance."""
    assert set(_reasons(inheritance, "--owner", "platform")) == {
        "requirement:mid",
        "requirement:spike",
    }
