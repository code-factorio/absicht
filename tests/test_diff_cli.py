"""``ab diff REF_A REF_B``: what changed in the design, as elements rather than lines.

What these tests pin, per ``docs/tasks/43-diff.md``:

- against a throwaway git fixture with two commits: an added requirement is
  an ``Added`` change, an interface whose ``contract`` moved is a
  ``FieldChanged``, and a changed ``state`` is a ``StateChanged``
  specifically — the spec calls state transitions out by name, so they are
  their own change shape, not one ``FieldChanged`` among others;
- ``--scope`` and ``--kind`` each independently narrow the compared elements;
- ``REF_A == REF_B`` is an empty answer and ``OK``, not an error — no change
  found is information;
- ``--format json`` is the ``format_version`` envelope of
  ``docs/tasks/00-conventions.md``, ``--json`` folds into a default
  ``--format`` without overriding an explicit one (docs/adr/0001), and
  ``--format md`` is the changelog-shaped document;
- an unknown ``--scope`` ref, or a rev that does not resolve, is ``USAGE``,
  the exit-code table's broken invocation.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.models.design import FORMAT_VERSION

runner = CliRunner()

# The whole answer for the fixture below, in the one order the command spells
# it: additions, removals, then per-element changes in id order, state before
# fields.
FULL_TEXT = [
    "+ req:refunds",
    "- req:bulk-export",
    "~ component:catalog title: Catalog -> Catalog, retitled",
    "~ interface:order-events contract: contracts/order-v1.md -> contracts/order-v2.md",
    "~ req:cancel-orders state: unknown -> specified",
    '~ req:cancel-orders actors: [] -> ["actor:customer"]',
]


def _git(repo: Path, *args: str) -> str:
    """Fixture plumbing: run git in ``repo``, failing loudly if it does not."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def history(tmp_path: Path) -> tuple[Path, str, str]:
    """A throwaway repo whose store moved in every way ``ab diff`` names: one
    requirement added, one dropped, one interface's contract rewritten, one
    element's state advanced, one requirement gaining the actor it serves —
    plus one component retitled outside the requirements' corner of the graph,
    the row ``--kind`` and ``--scope`` narrowing are pinned against.
    """
    repo = tmp_path / "repo"
    store = repo / ".absicht"
    for kind in ("actors", "components", "interfaces", "requirements"):
        (store / kind).mkdir(parents=True)
    (store / "design.yaml").write_text(
        "format_version: 1\nid: design:tiny\ntitle: Tiny\nversion: 0.1.0\n", encoding="utf-8"
    )

    def write(rel: str, front: str) -> None:
        (store / rel).write_text(f"---\n{front}\n---\n", encoding="utf-8")

    write(
        "actors/customer.md",
        "id: actor:customer\ntitle: Customer\nstate: specified\nactor_kind: person\n",
    )
    write(
        "components/orders.md",
        "id: component:orders\ntitle: Orders\nstate: specified\nlevel: container\n",
    )
    write(
        "components/catalog.md",
        "id: component:catalog\ntitle: Catalog\nstate: specified\nlevel: container\n",
    )
    write(
        "interfaces/order-events.md",
        "id: interface:order-events\ntitle: Order events\nstate: specified\n"
        "style: event\ndeclared_by: component:orders\ncontract: contracts/order-v1.md\n",
    )
    write(
        "requirements/cancel-orders.md",
        "id: req:cancel-orders\ntitle: Orders can be cancelled\nstate: unknown\n"
        "statement: A customer must be able to cancel an order.\n",
    )
    write(
        "requirements/bulk-export.md",
        "id: req:bulk-export\ntitle: Bulk export\nstate: specified\n"
        "statement: An operator must be able to export every order.\n",
    )
    _git(repo, "init", "-q", "-b", "main")
    # A bare CI machine has no git identity, and commits must not try to sign.
    _git(repo, "config", "user.email", "tests@absicht.invalid")
    _git(repo, "config", "user.name", "absicht tests")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c1")
    first = _git(repo, "rev-parse", "HEAD").strip()

    write(
        "requirements/refunds.md",
        "id: req:refunds\ntitle: Orders can be refunded\nstate: specified\n"
        "statement: A customer must be able to ask for a refund.\n",
    )
    (store / "requirements/bulk-export.md").unlink()
    write(
        "interfaces/order-events.md",
        "id: interface:order-events\ntitle: Order events\nstate: specified\n"
        "style: event\ndeclared_by: component:orders\ncontract: contracts/order-v2.md\n",
    )
    write(
        "requirements/cancel-orders.md",
        "id: req:cancel-orders\ntitle: Orders can be cancelled\nstate: specified\n"
        "statement: A customer must be able to cancel an order.\n"
        "actors:\n- actor:customer\n",
    )
    write(
        "components/catalog.md",
        "id: component:catalog\ntitle: Catalog, retitled\nstate: specified\nlevel: container\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c2")
    second = _git(repo, "rev-parse", "HEAD").strip()
    return store, first, second


def _diff(store: Path, ref_a: str, ref_b: str, *flags: str) -> Any:
    return runner.invoke(app, ["--store", str(store), "diff", ref_a, ref_b, *flags])


def _document(store: Path, ref_a: str, ref_b: str, *flags: str) -> dict[str, Any]:
    """The ``--format json`` answer, with exit code and envelope asserted once
    here rather than in every test below."""
    result = _diff(store, ref_a, ref_b, "--format", "json", *flags)
    assert result.exit_code == ExitCode.OK
    document = json.loads(result.stdout)
    assert document["format_version"] == FORMAT_VERSION
    return document


# --- the changes -----------------------------------------------------------------


def test_added_contract_and_state_come_back_as_their_own_change_shapes(
    history: tuple[Path, str, str],
) -> None:
    """One line per change, and ``state`` is spelled as a state transition —
    never as a ``FieldChanged`` on a field named ``state``, which is the
    collapse the spec says a dedicated change shape exists to avoid."""
    store, first, second = history

    result = _diff(store, first, second)

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == FULL_TEXT


def test_kind_narrows_the_compared_elements(history: tuple[Path, str, str]) -> None:
    store, first, second = history

    result = _diff(store, first, second, "--kind", "req")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "+ req:refunds",
        "- req:bulk-export",
        "~ req:cancel-orders state: unknown -> specified",
        '~ req:cancel-orders actors: [] -> ["actor:customer"]',
    ]


def test_scope_narrows_the_compared_elements(history: tuple[Path, str, str]) -> None:
    """``component:catalog`` points at nothing, so its subtree is itself alone:
    the retitling is in, the requirements and the interface are out."""
    store, first, second = history

    result = _diff(store, first, second, "--scope", "component:catalog")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "~ component:catalog title: Catalog -> Catalog, retitled",
    ]


def test_equal_revisions_are_an_empty_diff_not_an_error(history: tuple[Path, str, str]) -> None:
    store, _, second = history

    text = _diff(store, second, second)
    document = _document(store, second, second)

    assert text.exit_code == ExitCode.OK
    assert text.stdout == ""
    assert document["changes"] == []


# --- the formats -----------------------------------------------------------------


def test_json_envelopes_the_changes(history: tuple[Path, str, str]) -> None:
    store, first, second = history

    document = _document(store, first, second)

    assert document["from"] == first
    assert document["to"] == second
    assert document["changes"] == [
        {"type": "added", "kind": "req", "ref": "req:refunds"},
        {"type": "removed", "kind": "req", "ref": "req:bulk-export"},
        {
            "type": "field",
            "ref": "component:catalog",
            "field": "title",
            "before": "Catalog",
            "after": "Catalog, retitled",
        },
        {
            "type": "field",
            "ref": "interface:order-events",
            "field": "contract",
            "before": "contracts/order-v1.md",
            "after": "contracts/order-v2.md",
        },
        {
            "type": "state",
            "ref": "req:cancel-orders",
            "before": "unknown",
            "after": "specified",
        },
        {
            "type": "field",
            "ref": "req:cancel-orders",
            "field": "actors",
            "before": [],
            "after": ["actor:customer"],
        },
    ]


def test_json_folds_into_a_default_format_only(history: tuple[Path, str, str]) -> None:
    store, first, second = history

    folded = _diff(store, first, second, "--json")
    explicit = _diff(store, first, second, "--format", "text", "--json")

    assert folded.exit_code == ExitCode.OK
    assert json.loads(folded.stdout)["changes"]
    assert explicit.stdout.splitlines() == FULL_TEXT


def test_md_is_a_changelog_shaped_document(history: tuple[Path, str, str]) -> None:
    """One section per change shape, in the spec's own framing — decisions
    added, state transitions — and only the sections that have content."""
    store, first, second = history

    result = _diff(store, first, second, "--format", "md")

    assert result.exit_code == ExitCode.OK
    assert result.stdout.splitlines() == [
        "## Added",
        "",
        "- `req:refunds`",
        "",
        "## Removed",
        "",
        "- `req:bulk-export`",
        "",
        "## State transitions",
        "",
        "- `req:cancel-orders`: unknown -> specified",
        "",
        "## Changed",
        "",
        "- `component:catalog` — title: Catalog -> Catalog, retitled",
        "- `interface:order-events` — contract: contracts/order-v1.md -> contracts/order-v2.md",
        '- `req:cancel-orders` — actors: [] -> ["actor:customer"]',
    ]


# --- broken invocations ----------------------------------------------------------


def test_an_unknown_scope_ref_is_a_usage_error(history: tuple[Path, str, str]) -> None:
    """An empty answer would read as "nothing moved under it", which is a
    different claim than "no such element" — the same line `show`, `trace` and
    `render --scope` draw."""
    store, first, second = history

    result = _diff(store, first, second, "--scope", "component:ghost")

    assert result.exit_code == ExitCode.USAGE
    assert "--scope" in result.stderr
    assert result.stdout == ""


def test_a_rev_that_does_not_resolve_is_a_usage_error(history: tuple[Path, str, str]) -> None:
    store, _, second = history

    result = _diff(store, "no-such-ref", second)

    assert result.exit_code == ExitCode.USAGE
    assert "no-such-ref" in result.stderr
    assert result.stdout == ""
