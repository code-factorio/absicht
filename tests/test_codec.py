"""The on-disk spelling of a record: front matter, body, and error translation.

The format itself is pinned in `docs/tasks/00-conventions.md`; what these tests
add are the decisions that document left open (what a body without front matter
means, which delimiter wins) and the promise the layer above depends on: the
only exception that escapes `absicht.codec` is `CodecError`.
"""

from __future__ import annotations

from datetime import date

import pytest

from absicht.codec import (
    CodecError,
    dump_element,
    dump_singleton,
    parse_element,
    parse_singleton,
)
from absicht.models import (
    Component,
    Criterion,
    DataEntity,
    Decision,
    DecisionStatus,
    Element,
    External,
    ExternalKind,
    FieldSpec,
    Marker,
    Milestone,
    NonFunctional,
    QualityAttribute,
    Question,
    Record,
    Rejection,
    Requirement,
    ResolutionMethod,
    Reversibility,
    Seam,
    SeamStyle,
    State,
    Story,
    System,
    Unit,
    UnitWatermark,
)

# One representative element per Kind, each carrying the field shapes its kind
# adds (dates, nested records, markdown bodies) so a round trip exercises more
# than id-and-title. `source` is the store-relative path the loader would set.
ELEMENTS: dict[str, tuple[Element, str]] = {
    "requirement": (
        Requirement(
            id="requirement:cancel-orders",
            source="requirements/cancel-orders.md",
            title="Orders can be cancelled",
            state=State.SPECIFIED,
            realized_by=("component:cancellation",),
            body="A customer may cancel an order while it can still be refunded.",
        ),
        "requirements/cancel-orders.md",
    ),
    "nfr": (
        NonFunctional(
            id="nfr:cancel-latency",
            source="non_functionals/cancel-latency.md",
            title="Cancellation stays fast under load",
            attribute=QualityAttribute.LATENCY,
            scope=("component:cancellation",),
            stimulus="1000 concurrent cancellations",
            measure="p99 response time",
            target="< 200ms",
        ),
        "non_functionals/cancel-latency.md",
    ),
    "story": (
        Story(
            id="story:cancel-order",
            source="stories/cancel-order.md",
            title="Cancel an order",
            actor="customer",
            outcome="the order is cancelled and the refund starts",
            satisfies=("requirement:cancel-orders",),
            acceptance=(
                Criterion(
                    id="story:cancel-order#ac-1",
                    when="the customer cancels a refundable order",
                    then=("the order is cancelled", "the refund starts"),
                ),
            ),
        ),
        "stories/cancel-order.md",
    ),
    "component": (
        Component(
            id="component:cancellation",
            source="components/cancellation.md",
            title="Cancellation",
            responsibility="Decide whether an order can still be cancelled",
            consumes=("seam:order-events", "external:stripe"),
            provides=("seam:cancel-api",),
            implemented_by=("acme/orders#cancellation",),
        ),
        "components/cancellation.md",
    ),
    "seam": (
        Seam(
            id="seam:order-events",
            source="seams/order-events.md",
            title="Order events",
            style=SeamStyle.EVENT,
            provider="component:orders",
            consumers=("component:cancellation",),
            carries=("data:order",),
        ),
        "seams/order-events.md",
    ),
    "data": (
        DataEntity(
            id="data:order",
            source="data/order.md",
            title="Order",
            owner_component="component:orders",
            fields=(
                FieldSpec(name="id", type="uuid"),
                FieldSpec(name="status", type="string", note="lifecycle state"),
            ),
            identity=("id",),
        ),
        "data/order.md",
    ),
    "decision": (
        Decision(
            id="decision:event-log",
            source="decisions/event-log.md",
            title="Event log over in-place updates",
            status=DecisionStatus.ACCEPTED,
            decided_on=date(2026, 1, 15),
            reversibility=Reversibility.ONE_WAY,
            tags=("arch",),
            body="## Context\n\nThe audit trail is the product.\n\n## Consequences\n\nRead models project from the log.\n",
        ),
        "decisions/event-log.md",
    ),
    "rejection": (
        Rejection(
            id="rejection:sagas",
            source="rejections/sagas.md",
            title="No sagas for cancellation",
            applies_to=("component:cancellation",),
            rejected_on=date(2026, 2, 1),
            milestone="milestone:m1",
        ),
        "rejections/sagas.md",
    ),
    "question": (
        Question(
            id="question:refund-window",
            source="questions/refund-window.md",
            title="How long is the refund window?",
            method=ResolutionMethod.MEASURE,
            blocks=("story:cancel-order",),
            due_on=date(2026, 9, 1),
        ),
        "questions/refund-window.md",
    ),
    "milestone": (
        Milestone(
            id="milestone:m1",
            source="milestones/m1.md",
            title="Cancellation MVP",
            includes=("story:cancel-order",),
            scope=("component:cancellation",),
            done_when=("story:cancel-order#ac-1",),
        ),
        "milestones/m1.md",
    ),
    "external": (
        External(
            id="external:stripe",
            source="externals/stripe.md",
            title="Stripe",
            external_kind=ExternalKind.SERVICE,
            version="2026-03",
            assumptions=("idempotency keys are honored",),
            verified_on=date(2026, 1, 10),
            expires_on=date(2026, 7, 10),
        ),
        "externals/stripe.md",
    ),
}

# Singletons are plain YAML (`system.yaml`, a repo `.absicht` marker): no front
# matter, no body split, but the same round-trip promise.
SINGLETONS: dict[str, tuple[Record, type[Record]]] = {
    "system": (
        System(
            id="system:acme",
            title="ACME",
            purpose="Sell things, honestly",
            units=(Unit(id="unit:billing", repo="acme/billing"),),
            externals=("external:stripe",),
        ),
        System,
    ),
    "marker": (
        Marker(
            design="/srv/design",
            units=(UnitWatermark(id="unit:billing", at="milestone:m1", design_rev="abc123"),),
        ),
        Marker,
    ),
}


@pytest.mark.parametrize(("element", "path"), ELEMENTS.values(), ids=list(ELEMENTS))
def test_each_kind_survives_a_round_trip(element: Element, path: str) -> None:
    assert parse_element(dump_element(element), model=type(element), source=path) == element


@pytest.mark.parametrize(("record", "model"), SINGLETONS.values(), ids=list(SINGLETONS))
def test_singletons_survive_a_round_trip_as_plain_yaml(record: Record, model: type[Record]) -> None:
    assert parse_singleton(dump_singleton(record), model=model) == record


def test_front_matter_without_a_body_parses_to_an_empty_body() -> None:
    text = "---\nid: component:x\ntitle: X\n---\n"

    assert parse_element(text, model=Component, source="components/x.md").body == ""


def test_a_body_without_front_matter_is_refused() -> None:
    """Prose alone is not an element: `id` and `title` live in the front matter."""

    with pytest.raises(CodecError, match="front matter"):
        parse_element("Just prose, no delimiters.\n", model=Component, source="components/x.md")


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(CodecError, match="front matter"):
        parse_element("", model=Component, source="components/x.md")


def test_empty_front_matter_reports_the_missing_fields() -> None:
    """`---\n---\n` is well-shaped but contentless: the error must name what is absent."""

    with pytest.raises(CodecError, match=r"\bid\b"):
        parse_element("---\n---\n", model=Component, source="components/x.md")


def test_unterminated_front_matter_is_refused() -> None:
    with pytest.raises(CodecError, match="unterminated"):
        parse_element("---\nid: component:x\n", model=Component, source="components/x.md")


def test_front_matter_that_is_not_a_mapping_is_refused() -> None:
    with pytest.raises(CodecError, match="mapping"):
        parse_element("---\n- one\n- two\n---\n", model=Component, source="components/x.md")


def test_a_yaml_syntax_error_is_translated_not_leaked() -> None:
    with pytest.raises(CodecError, match="invalid YAML"):
        parse_element("---\nid: [unclosed\n---\n", model=Component, source="components/x.md")


def test_a_validation_error_is_translated_not_leaked() -> None:
    """`load` builds findings from the message, so it must name the offending field."""

    with pytest.raises(CodecError, match=r"validation failed: id\b"):
        parse_element(
            "---\nid: not-a-ref\ntitle: X\n---\n", model=Component, source="components/x.md"
        )


def test_singleton_errors_are_translated_too() -> None:
    with pytest.raises(CodecError, match="invalid YAML"):
        parse_singleton("units: [unclosed", model=System)
    with pytest.raises(CodecError, match="mapping"):
        parse_singleton("- just\n- a\n- list", model=System)
    with pytest.raises(CodecError, match=r"validation failed: title\b"):
        parse_singleton("id: system:acme", model=System)


def test_field_order_is_declaration_order_regardless_of_construction() -> None:
    """Diffs stay small only if equal elements always dump to equal text."""

    by_kwargs = Component(
        implemented_by=("acme/orders#billing",),
        title="Billing",
        id="component:billing",
    )
    by_reversed_dict = Component.model_validate(
        {
            "implemented_by": ["acme/orders#billing"],
            "title": "Billing",
            "id": "component:billing",
        }
    )

    dumped = dump_element(by_kwargs)
    assert dumped == dump_element(by_reversed_dict)

    # Top-level keys sit at column 0; sequence items ("- x") and wrapped
    # continuations are indented or dashed, so this picks out just the keys.
    lines = dumped.splitlines()
    keys = [
        line.split(":", 1)[0]
        for line in lines[1 : lines.index("---", 1)]
        if line and not line.startswith((" ", "-"))
    ]
    assert keys == [name for name in Component.model_fields if name not in ("source", "body")]
