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
- ``--format json`` is the ``format_version`` envelope of
  ``00-conventions.md``, and ``--json`` folds into a default ``--format``
  without overriding an explicit one (docs/adr/0001);
- the ``Kind``/``Design`` field-name mismatches (``req`` vs
  ``requirements``, ``term`` vs ``glossary``, ``data`` vs ``data_entities``)
  are handled — pinned by asking for each and, for a kind no fixture stores
  yet, getting an empty answer rather than a crash.

Since the model addendum: ``resource`` and ``behavior`` list like every other
kind; ``--lifecycle`` filters the behavior's second axis (§5 — a behavior can
be perfectly `specified` and no longer true); §4.1's derived scope joins the
behavior row as a column and as a ``--scope`` filter, and a superseded
behavior's row carries §5's visible mark; and §7's owner inheritance
joins `--owner`/`--unowned`, so an unowned `unknown` answers to the single
element referencing it that carries an owner — one level, never stored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.models.design import FORMAT_VERSION

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
        "component:legacy",
        "component:legacy-billing",
        "component:shadow-report",
    ]
    # `behavior:reconciliation-fires` is `observed`: under any-of it survives
    # a second `--state` it does not have, which a last-value-wins reading
    # (or an exact single match) would drop.
    assert _ids(BROWNFIELD, "behavior", "--state", "observed", "--state", "specified") == [
        "behavior:reconciliation-fires"
    ]
    assert _ids(BROWNFIELD, "req", "--state", "specified") == []


def test_confidence_is_exact() -> None:
    """Neither fixture mixes confidences inside one store — clean is
    `reviewed` throughout, brownfield `assumed` — so exactness reads across
    the two: the level a store carries answers with the whole kind, and the
    other level answers with nothing rather than being ignored."""
    assert _ids(CLEAN, "req", "--confidence", "reviewed") == [
        "req:browse-catalog",
        "req:cancel-orders",
    ]
    assert _ids(CLEAN, "req", "--confidence", "assumed") == []
    assert _ids(BROWNFIELD, "req", "--confidence", "assumed") == [
        "req:audit-trail",
        "req:refund-parity",
    ]


def test_unowned_finds_the_ungoverned_unknown() -> None:
    """brownfield's unowned requirement is the `unknown` `ab gaps` exists to
    surface, and nothing points at it, so no owner is inherited either.
    `--owner` is its mirror: the rest of the store answers to sam, and a name
    nobody carries answers nothing — an ignored flag would list every
    element of the kind instead."""
    assert _ids(BROWNFIELD, "req", "--unowned") == ["req:refund-parity"]
    assert _ids(BROWNFIELD, "req", "--owner", "sam") == ["req:audit-trail"]
    assert _ids(BROWNFIELD, "req", "--owner", "anyone") == []


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
    """`data:audit-log` is the element nothing points at — what brownfield was
    built around. The components the observed behavior watches are not
    orphaned: an observation is a reference, and what points at them is what
    gives them meaning. `req:audit-trail` is pointed at by the behavior that
    realizes it and the component that implements it, so it is not orphaned
    either despite being `observed`: `--orphaned` reads `referenced_by`, not
    `state` — and `req:refund-parity`, which nothing points at, is."""
    assert _ids(BROWNFIELD, "component", "--orphaned") == []
    assert _ids(BROWNFIELD, "data", "--orphaned") == ["data:audit-log"]
    assert _ids(BROWNFIELD, "req", "--orphaned") == ["req:refund-parity"]


def test_milestone_returns_exactly_its_scope() -> None:
    """`milestone:m1`'s scope is `component:orders` and `component:cancellation`;
    the filter intersects scope with KIND rather than answering with the scope
    itself."""
    assert _ids(CLEAN, "component", "--milestone", "milestone:m1") == [
        "component:cancellation",
        "component:orders",
    ]
    assert _ids(CLEAN, "interface", "--milestone", "milestone:m1") == []


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
    assert result.stdout == (
        "component:legacy\ncomponent:legacy-billing\ncomponent:shadow-report\n"
    )


def test_an_empty_answer_prints_nothing_at_all() -> None:
    """No blank line where an id would be: `"\n".splitlines()` yields one
    empty string, so a lone newline would hand xargs one empty argument."""
    result = _list(BROWNFIELD, "req", "--state", "specified", "--format", "ids")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == ""


def test_json_envelopes_the_selected_elements() -> None:
    result = _list(CLEAN, "req", "--format", "json", "--state", "specified")

    document = json.loads(result.stdout)
    assert document["format_version"] == FORMAT_VERSION
    assert document["kind"] == "req"
    assert [element["id"] for element in document["elements"]] == [
        "req:browse-catalog",
        "req:cancel-orders",
    ]
    # The elements themselves, not just their ids: a field a filter keyed on
    # is a field the output can be checked against.
    assert document["elements"][1]["confidence"] == "reviewed"


def test_json_folds_into_a_default_format_only() -> None:
    folded = _list(CLEAN, "component", "--json")
    explicit = _list(CLEAN, "component", "--format", "ids", "--json")

    assert folded.exit_code == ExitCode.OK
    assert json.loads(folded.stdout)["kind"] == "component"
    assert explicit.stdout == (
        "component:acme\ncomponent:cancellation\ncomponent:catalog\ncomponent:orders\n"
    )


def test_text_is_one_row_per_element_with_id_state_and_title() -> None:
    result = _list(BROWNFIELD, "component")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "component:legacy          observed  Legacy billing",
        "component:legacy-billing  observed  Billing engine",
        "component:shadow-report   observed  Shadow report",
    ]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("term", ["term:order"]),  # glossary
        ("req", ["req:browse-catalog", "req:cancel-orders"]),  # requirements
        ("quality", ["quality:cancel-latency"]),  # qualities
        ("data", ["data:order"]),  # data_entities
        ("external", []),  # external_services — clean stores none
    ],
)
def test_a_kind_maps_to_its_differently_spelled_field(kind: str, expected: list[str]) -> None:
    """A `Kind`'s value is its ref prefix, and several `Design` fields are
    spelled differently from it (`term`/`glossary`, `req`/`requirements`,
    `data`/`data_entities`, `external`/`external_services`). The lookup is a
    table, not a pluralisation, so each answers with its own elements — and a
    kind no fixture stores yet answers empty rather than crashing on the
    misspelling."""
    assert _ids(CLEAN, kind) == expected


# --- the addendum's kinds --------------------------------------------------------


def test_the_new_kinds_list_like_every_other_kind() -> None:
    """`resource` and `behavior` are plain `Kind`s — same rows, same envelope
    — and the behavior's own second axis rides in the element like any
    field, which is what `--lifecycle` then selects on."""
    assert _ids(CLEAN, "resource") == ["resource:order-cache", "resource:order-stream"]

    document = json.loads(_list(CLEAN, "behavior", "--format", "json").stdout)

    assert document["kind"] == "behavior"
    by_id = {element["id"]: element for element in document["elements"]}
    assert by_id["behavior:order-placed"]["lifecycle"] == "superseded"


def test_lifecycle_filters_behaviors_second_axis() -> None:
    """`--lifecycle` is the axis `state` is not (addendum §5).
    `behavior:order-placed` is the clean fixture's superseded one; its
    replacement and the other two behaviors stay active."""
    assert _ids(CLEAN, "behavior", "--lifecycle", "superseded") == ["behavior:order-placed"]
    assert _ids(CLEAN, "behavior", "--lifecycle", "active") == [
        "behavior:catalog-browsable",
        "behavior:order-cancelled",
        "behavior:order-placed-v2",
    ]


def test_lifecycle_on_a_kind_without_the_axis_is_usage() -> None:
    """Only behaviors carry the axis. Silently ignoring the flag would answer
    `ab list component --lifecycle superseded` with every component — a lie
    about the filter, worse than a refusal."""
    result = _list(CLEAN, "component", "--lifecycle", "active")

    assert result.exit_code == ExitCode.USAGE
    assert "--lifecycle" in result.stderr
    assert result.stdout == ""


# --- derived scope (model addendum §4.1) -----------------------------------------


def test_the_behavior_rows_gain_the_derived_scope_column() -> None:
    """`scope` is computed, never authored (§4.1), so it joins the behavior
    row between state and title — the classification a reader triages by —
    and the superseded behavior's row carries §5's visible mark. Every other
    kind's row stays three columns wide."""
    behaviors = _list(CLEAN, "behavior").stdout.splitlines()
    components = _list(CLEAN, "component").stdout.splitlines()

    assert behaviors == [
        "behavior:catalog-browsable  specified  local  Browsing the catalog signed out",
        "behavior:order-cancelled    specified  system  Cancelling an unshipped order",
        "behavior:order-placed       specified  local  Placing an order (the first cut) [superseded]",
        "behavior:order-placed-v2    specified  system  Placing an order",
    ]
    assert components == [
        "component:acme          specified  ACME",
        "component:cancellation  specified  Cancellation",
        "component:catalog       specified  Catalog",
        "component:orders        specified  Orders",
    ]


def test_scope_filters_the_derived_classification() -> None:
    """`--scope` selects on the same §4.1 classification the column shows: a
    behavior whose direct non-behavior touches are one component is `local`,
    and anything wider — two resources, or a resource alone — is `system`."""
    assert _ids(CLEAN, "behavior", "--scope", "local") == [
        "behavior:catalog-browsable",
        "behavior:order-placed",
    ]
    assert _ids(CLEAN, "behavior", "--scope", "system") == [
        "behavior:order-cancelled",
        "behavior:order-placed-v2",
    ]


def test_scope_on_a_kind_without_the_classification_is_usage() -> None:
    """Only behaviors have a scope to filter on. Silently ignoring the flag
    would answer `ab list component --scope local` with every component — the
    same lie `--lifecycle` on a component would tell."""
    result = _list(CLEAN, "component", "--scope", "local")

    assert result.exit_code == ExitCode.USAGE
    assert "--scope" in result.stderr
    assert result.stdout == ""


def test_json_carries_the_derived_scope_beside_the_element() -> None:
    """§4.1's answer rides in `--json` additively (50-addendum-conventions:
    derived values appear in `--json`), beside the element's own fields — and
    only for the kind that has one."""
    document = json.loads(_list(CLEAN, "behavior", "--format", "json").stdout)
    plain = json.loads(_list(CLEAN, "resource", "--format", "json").stdout)

    by_id = {element["id"]: element for element in document["elements"]}
    assert by_id["behavior:catalog-browsable"]["scope"] == "local"
    assert by_id["behavior:order-cancelled"]["scope"] == "system"
    assert "scope" not in plain["elements"][0]


# --- §7 owner inheritance --------------------------------------------------------


@pytest.fixture
def inheritance(tmp_path: Path) -> Path:
    """§7's owner inheritance in the smallest store that holds it:
    `req:inherits` is an unowned `unknown` whose one referencing element
    carries an owner; `req:self-owned` has an owner of its own;
    `component:contested` is referenced by two elements with two different
    owners. No fixture pairs an unowned `unknown` with an owned referencing
    element, and growing one would move other tickets' exact-match worklist
    assertions — the case gets a store of its own instead."""
    root = tmp_path / "inheritance"
    _write(
        root,
        "design.yaml",
        "format_version: 1\nid: design:inheritance\ntitle: Inheritance\nversion: 0.1.0\n",
    )
    _write(
        root,
        "requirements/inherits.md",
        "---\nid: req:inherits\ntitle: Inherits\nstate: unknown\n"
        "statement: Somebody must say what this means.\n---\n",
    )
    _write(
        root,
        "requirements/self-owned.md",
        "---\nid: req:self-owned\ntitle: Self owned\nstate: unknown\nowner: qa\n"
        "statement: Somebody must say what this one means too.\n---\n",
    )
    _write(
        root,
        "components/contested.md",
        "---\nid: component:contested\ntitle: Contested\nstate: unknown\nlevel: container\n---\n",
    )
    _write(
        root,
        "components/caller-a.md",
        "---\nid: component:caller-a\ntitle: Caller A\nstate: specified\nowner: team-a\n"
        "level: container\nrelates:\n- to: component:contested\n  type: calls\n---\n",
    )
    _write(
        root,
        "components/caller-b.md",
        "---\nid: component:caller-b\ntitle: Caller B\nstate: specified\nowner: team-b\n"
        "level: container\nrelates:\n- to: component:contested\n  type: calls\n---\n",
    )
    _write(
        root,
        "components/carrier.md",
        "---\nid: component:carrier\ntitle: Carrier\nstate: specified\nowner: platform\n"
        "level: container\nrelates:\n- to: req:inherits\n  type: implements\n"
        "- to: req:self-owned\n  type: implements\n---\n",
    )
    return root


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_owner_groups_the_unknown_that_inherits_its_referencers(
    inheritance: Path,
) -> None:
    """`--owner platform` answers with `req:inherits` even though its own
    `owner` is empty: grouping by owner is where §7's inheritance lives,
    and the group that would own the unknown is the one that referenced it."""
    assert _ids(inheritance, "req", "--owner", "platform") == ["req:inherits"]


def test_an_element_with_its_own_owner_is_never_overridden(inheritance: Path) -> None:
    """`component:carrier` (owned by platform) implements both requirements,
    but `req:self-owned` answers to qa alone: inheritance is for the
    ownerless, and an authored owner always stands."""
    assert _ids(inheritance, "req", "--owner", "qa") == ["req:self-owned"]


def test_unowned_means_no_owner_not_even_an_inherited_one(inheritance: Path) -> None:
    """The inherited side of the same coin: an unknown that answers to
    platform leaves `--unowned`, while `component:contested` — referenced by
    an owner and another owner — stays ownerless: ambiguity is not a guess."""
    assert _ids(inheritance, "req", "--unowned") == []
    assert _ids(inheritance, "component", "--unowned") == ["component:contested"]
