"""``absicht.render``: the element view behind ``ab show`` and the site's pages.

The command contract — exit codes, flags, the bytes on stdout — lives in
``tests/test_show_cli.py``. What is pinned here is the view itself, the shape
``docs/tasks/26-render-site.md`` builds its element pages on ("literally
reuse 21-show.md's function"):

- ``--depth`` bounds the *outgoing* side only; the inbound side is one hop at
  any depth, because expanding both directions is the pathfinding ``ab trace``
  owns and ``show`` deliberately does not (``docs/tasks/21-show.md`` left the
  choice open; this is the one it made, and the command's ``--help`` says so);
- expansion stops when the budget runs out, not when a walk revisits a node —
  a seam's provider provides that seam right back, and the view of a cyclic
  graph is a bounded tree, not a search;
- a dangling ref resolves to no neighbour on either side, the same policy
  ``Index.referenced_by`` already holds: reporting dangling refs is ``ab
  check``'s job. ``broken/`` cannot reach this through the CLI (its two
  unreadable files are ``build``'s refusal), so the policy is pinned here on
  the folded design.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from absicht.load import load_store
from absicht.models import SCHEMA_VERSION, Design
from absicht.render import UnknownRefError, neighbourhood
from absicht.resolve import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "systems"


@pytest.fixture
def clean() -> Design:
    """The folded ``clean/`` design the assertions below walk."""
    return resolve(load_store(FIXTURES / "clean"))


def test_an_unknown_ref_raises_rather_than_answering_empty(clean: Design) -> None:
    """`ab show` maps this to `USAGE`: the caller asked for an element that is
    not there, which is a broken invocation, not a finding about the design."""

    with pytest.raises(UnknownRefError, match="component:ghost"):
        neighbourhood(clean, "component:ghost", depth=1)


def test_the_outgoing_side_expands_to_the_asked_depth_and_no_further(clean: Design) -> None:
    view = neighbourhood(clean, "seam:order-events", depth=2)

    assert [(hop.field, hop.other.id) for hop in view.outgoing] == [
        ("provider", "component:orders"),
        ("consumers", "component:cancellation"),
        ("carries", "data:order"),
    ]
    orders = view.outgoing[0]
    assert [(hop.field, hop.other.id) for hop in orders.deeper] == [
        ("contains", "component:catalog"),
        ("provides", "seam:order-events"),
        ("owns_data", "data:order"),
    ]
    # Depth 2 stops at the fringe: `orders` provides this very seam right
    # back — the cycle the budget must bound, not chase — and every hop at the
    # fringe is a leaf. Expanding those again is depth 3's job.
    assert all(hop.deeper == () for hop in orders.deeper)


def test_depth_zero_leaves_the_outgoing_side_unfollowed(clean: Design) -> None:
    """Zero hops means the element's own refs are not followed — the view is
    the element plus whoever points at it, and `--depth 0` must not quietly
    mean the same as the default."""

    view = neighbourhood(clean, "component:cancellation", depth=0)

    assert view.outgoing == ()
    assert view.incoming != ()


def test_the_inbound_side_stays_one_hop_at_any_depth(clean: Design) -> None:
    """A depth that deep would find more if the inbound side expanded too —
    `story:cancel-order` is satisfied by nothing here, but `seam:order-events`
    is pointed at by three elements whose own refs go further out."""

    view = neighbourhood(clean, "seam:order-events", depth=5)

    assert [(link.field, link.other.id) for link in view.incoming] == [
        ("touches", "story:cancel-order"),
        ("consumes", "component:cancellation"),
        ("provides", "component:orders"),
    ]


def test_a_dangling_ref_resolves_to_no_neighbour() -> None:
    design = resolve(load_store(FIXTURES / "broken"))

    view = neighbourhood(design, "component:dangling", depth=2)

    # `dangling`'s one ref is `contains: component:ghost`, which no file
    # defines: it must not appear as a neighbour, and the empty view is still
    # a successful one — `ab show` reports neighbourhoods, `ab check` reports
    # the ghost.
    assert view.outgoing == ()


def test_json_carries_the_full_view_and_the_body_flag(clean: Design) -> None:
    view = neighbourhood(clean, "requirement:cancel-orders", depth=2)

    with_body = view.render_json(include_body=True)
    without_body = view.render_json(include_body=False)

    assert with_body["schema_version"] == SCHEMA_VERSION
    assert with_body["element"]["body"].startswith("A customer may cancel")
    assert "body" not in without_body["element"]
    hop = with_body["points_at"][0]
    assert hop["field"] == "realized_by"
    assert hop["target"]["id"] == "component:cancellation"
    # Neighbours carry their fields but never prose or provenance: the body is
    # the focus element's, and where a neighbour lives is `source`'s story.
    assert "body" not in hop["target"]
    assert "source" not in hop["target"]
    assert [(deeper["field"], deeper["target"]["id"]) for deeper in hop["deeper"]] == [
        ("consumes", "seam:order-events")
    ]
    assert hop["deeper"][0]["deeper"] == []
    assert [(link["field"], link["source"]["id"]) for link in with_body["referenced_by"]] == [
        ("satisfies", "story:cancel-order")
    ]
