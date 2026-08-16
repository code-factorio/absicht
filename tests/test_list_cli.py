"""``ab list KIND``: one kind's elements, filtered, in three formats.

What these tests pin, per ``docs/tasks/22-list.md``:

- every filter independently as a predicate AND: ``--state`` any-of over the
  repeatable flag, ``--confidence`` and ``--owner`` exact, ``--unowned`` the
  ownerless, ``--tag`` any-of over ``Element.tags``, ``--milestone`` scope
  membership, ``--orphaned`` ``Index.orphaned``'s answer;
- ``--owner`` and ``--unowned`` together is ``USAGE``;
- ``--format ids`` is exactly one id per line and nothing else — the format an
  agent pipes to ``xargs``, so an empty answer is no output at all rather
  than a blank line;
- ``--format json`` is the ``schema_version`` envelope of
  ``00-conventions.md``, and ``--json`` folds into a default ``--format``
  without overriding an explicit one (docs/adr/0001);
- the one ``Kind``/``Design`` field-name mismatch (``nfr`` vs
  ``non_functionals``) is handled — pinned by asking for a kind no fixture
  stores yet and getting an empty answer rather than a crash.
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


def _list(store: Path, kind: str, *flags: str) -> Any:
    return runner.invoke(app, ["--store", str(store), "list", kind, *flags])


def _ids(store: Path, kind: str, *flags: str) -> list[str]:
    """The answer as ``--format ids`` spells it, with the exit code asserted
    once here rather than in every filter test."""
    result = _list(store, kind, "--format", "ids", *flags)
    assert result.exit_code == ExitCode.OK
    return result.stdout.splitlines()


def test_state_matches_any_of_the_repeatable_flag_s_values() -> None:
    assert _ids(BROWNFIELD, "component", "--state", "observed") == [
        "component:legacy-billing",
        "component:shadow-report",
    ]
    # `story:reconcile-billing` is `observed`: under any-of it survives a
    # second `--state` it does not have, which a last-value-wins reading
    # (or an exact single match) would drop.
    assert _ids(BROWNFIELD, "story", "--state", "observed", "--state", "specified") == [
        "story:reconcile-billing"
    ]
    assert _ids(BROWNFIELD, "requirement", "--state", "specified") == []


def test_confidence_is_exact() -> None:
    assert _ids(CLEAN, "requirement", "--confidence", "reviewed") == ["requirement:cancel-orders"]
    assert _ids(CLEAN, "requirement", "--confidence", "assumed") == ["requirement:browse-catalog"]


def test_unowned_finds_the_ungoverned_unknown() -> None:
    """brownfield's unowned requirement is the `unknown` `ab gaps` exists to
    surface. No fixture element carries an owner, so the honest positive for
    `--owner` is that it applies and answers nothing — an ignored flag would
    list every element of the kind instead."""
    assert _ids(BROWNFIELD, "requirement", "--unowned") == ["requirement:audit-trail"]
    assert _ids(BROWNFIELD, "requirement", "--owner", "anyone") == []


def test_owner_and_unowned_together_is_usage() -> None:
    result = _list(BROWNFIELD, "component", "--owner", "anyone", "--unowned")

    assert result.exit_code == ExitCode.USAGE
    assert "--owner" in result.stderr
    assert result.stdout == ""


def test_tag_filters_out_elements_without_the_tag() -> None:
    """No fixture element carries a tag, so one tag filters everything out —
    the one meaningful assertion available against the shared fixtures rather
    than an ad hoc store `00-conventions.md` says not to invent."""
    assert _ids(BROWNFIELD, "component", "--tag", "billing") == []


def test_orphaned_finds_the_disconnected_elements() -> None:
    """`component:legacy-billing`, `component:shadow-report` and
    `data:audit-log` are the elements nothing points at — what brownfield was
    built around. `requirement:audit-trail` is pointed at by its story, so it
    is not orphaned: `--orphaned` reads `referenced_by`, not `state`."""
    assert _ids(BROWNFIELD, "component", "--orphaned") == [
        "component:legacy-billing",
        "component:shadow-report",
    ]
    assert _ids(BROWNFIELD, "data", "--orphaned") == ["data:audit-log"]
    assert _ids(BROWNFIELD, "requirement", "--orphaned") == []


def test_milestone_returns_exactly_its_scope() -> None:
    """`milestone:m1`'s scope is `component:cancellation` alone; the filter
    intersects scope with KIND rather than answering with the scope itself."""
    assert _ids(CLEAN, "component", "--milestone", "milestone:m1") == ["component:cancellation"]
    assert _ids(CLEAN, "seam", "--milestone", "milestone:m1") == []


def test_an_unknown_milestone_ref_is_a_usage_error() -> None:
    """`REF` must name a milestone — an element of another kind or nothing at
    all is the same lookup miss, and the exit-code table reads it as a broken
    invocation, not an empty answer."""
    result = _list(CLEAN, "component", "--milestone", "component:orders")

    assert result.exit_code == ExitCode.USAGE
    assert "--milestone" in result.stderr
    assert result.stdout == ""


def test_ids_is_exactly_one_id_per_line() -> None:
    """No header, no padding, one trailing newline after the last id — the
    exact bytes an agent's `xargs ab show` depends on."""
    result = _list(BROWNFIELD, "component", "--format", "ids")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == "component:legacy-billing\ncomponent:shadow-report\n"


def test_an_empty_answer_prints_nothing_at_all() -> None:
    """No blank line where an id would be: `"\n".splitlines()` yields one
    empty string, so a lone newline would hand xargs one empty argument."""
    result = _list(BROWNFIELD, "requirement", "--state", "specified", "--format", "ids")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""


def test_json_envelopes_the_selected_elements() -> None:
    result = _list(CLEAN, "requirement", "--format", "json", "--state", "specified")

    document = json.loads(result.stdout)
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["kind"] == "requirement"
    assert [element["id"] for element in document["elements"]] == [
        "requirement:browse-catalog",
        "requirement:cancel-orders",
    ]
    # The elements themselves, not just their ids: a field a filter keyed on
    # is a field the output can be checked against.
    assert document["elements"][1]["confidence"] == "reviewed"


def test_json_folds_into_a_default_format_only() -> None:
    folded = _list(CLEAN, "component", "--json")
    explicit = _list(CLEAN, "component", "--format", "ids", "--json")

    assert folded.exit_code == ExitCode.OK
    assert json.loads(folded.stdout)["kind"] == "component"
    assert explicit.stdout == "component:cancellation\ncomponent:catalog\ncomponent:orders\n"


def test_text_is_one_row_per_element_with_id_state_and_title() -> None:
    result = _list(BROWNFIELD, "component")

    assert result.exit_code == ExitCode.OK
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert "component:legacy-billing" in lines[0]
    assert "observed" in lines[0]
    assert "Legacy billing" in lines[0]
    assert "component:shadow-report" in lines[1]


def test_the_nfr_kind_maps_to_its_differently_spelled_field() -> None:
    """`nfr` is the one `Kind` whose `Design` field is not its plural
    (`non_functionals`). No fixture stores an nfr yet, so the honest pin is
    that the lookup answers empty rather than crashing on the misspelling."""
    result = _list(CLEAN, "nfr", "--format", "ids")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""
