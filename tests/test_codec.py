"""The on-disk spelling of a record: front matter, body, edges, and errors.

`absicht.codec` is the only layer that knows a record has a file. What these
tests pin are the decisions the format leaves to it, and the promise every
layer above depends on:

- every kind the store can hold survives a round trip, `DIRECTORIES` included
  — a kind added to the model without a case here would be a directory
  nothing has ever read back;
- an element's file owns its outgoing edges. `relates` is lifted into whole
  `Relationship` records with the file as their source, and written back with
  the source dropped: saying it twice is how two files come to disagree;
- the loader owns provenance. `source` is stamped from the path, never read
  from the front matter, and the Markdown body lands in `body` on an element
  and in `text` on a note, which is all a note is;
- `design.yaml` is the header alone. Everything in `ASSEMBLED` is many files
  on disk, and a second copy in the header would drift on the first edit;
- the only exception that escapes this module is `CodecError`, split into the
  syntax and validation families `check` maps to its two rule ids.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from absicht.codec import (
    ASSEMBLED,
    DIRECTORIES,
    CodecError,
    CodecSyntaxError,
    CodecValidationError,
    document_schema,
    dump_design,
    dump_element,
    dump_singleton,
    parse_element,
    parse_singleton,
)
from absicht.models.design import (
    Actor,
    ActorKind,
    Assumption,
    Behavior,
    Component,
    ComponentLevel,
    Constraint,
    ConstraintKind,
    DataEntity,
    Decision,
    Design,
    Element,
    ExternalService,
    FieldSpec,
    Goal,
    Interface,
    InterfaceStyle,
    Library,
    Milestone,
    Note,
    Observation,
    Operation,
    Outcome,
    Priority,
    QualityAttribute,
    QualityRequirement,
    Question,
    Record,
    Rejection,
    Relationship,
    RelationshipType,
    Requirement,
    ResolutionMethod,
    Resource,
    ResourceKind,
    Reversibility,
    State,
    Term,
    Timing,
)
from absicht.models.layout import Layout, Position
from absicht.models.marker import Marker, Watermark

# One representative per store directory, each carrying the field shapes its
# kind adds — dates, nested records, Markdown bodies — so a round trip
# exercises more than an id and a title. `source` is the store-relative path
# the loader would stamp, which is why every case names it twice.
ELEMENTS: dict[str, tuple[Element | Note, str]] = {
    "glossary": (
        Term(
            id="term:order",
            source="glossary/order.md",
            title="Order",
            definition="A customer's request to buy, before it ships.",
            aliases=("basket",),
        ),
        "glossary/order.md",
    ),
    "actors": (
        Actor(
            id="actor:customer",
            source="actors/customer.md",
            title="Customer",
            actor_kind=ActorKind.PERSON,
            goals=("Buy a thing without talking to anybody.",),
        ),
        "actors/customer.md",
    ),
    "goals": (
        Goal(
            id="goal:cheap-orders",
            source="goals/cheap-orders.md",
            title="Ordering costs less to support",
            outcome="Ordering costs less to support",
            measure="support contacts per 100 orders",
            target="< 3",
            stakeholders=("actor:customer",),
            horizon=date(2026, 12, 31),
            body="Every contact about an order is an order the system failed to explain.",
        ),
        "goals/cheap-orders.md",
    ),
    "requirements": (
        Requirement(
            id="req:cancel-orders",
            source="requirements/cancel-orders.md",
            title="Cancel an order",
            state=State.SPECIFIED,
            statement="A customer must be able to cancel an order that has not shipped.",
            rationale="A cancellation nobody can do themselves becomes a support contact.",
            priority=Priority.MUST,
            actors=("actor:customer",),
        ),
        "requirements/cancel-orders.md",
    ),
    "qualities": (
        QualityRequirement(
            id="quality:cancel-latency",
            source="qualities/cancel-latency.md",
            title="Cancelling is immediate to a human",
            attribute=QualityAttribute.LATENCY,
            stimulus="1000 concurrent cancellations",
            measure="p99 response time",
            target="< 200 ms",
            scope=("component:cancellation",),
            evidence=("bench/cancel.py",),
        ),
        "qualities/cancel-latency.md",
    ),
    "constraints": (
        Constraint(
            id="constraint:gdpr-erasure",
            source="constraints/gdpr-erasure.md",
            title="A customer's data is erasable on request",
            statement="Personal data must be erasable within 30 days of a request.",
            constraint_kind=ConstraintKind.REGULATORY,
            imposed_by="GDPR Art. 17",
        ),
        "constraints/gdpr-erasure.md",
    ),
    "behaviors": (
        Behavior(
            id="behavior:order-placed-v2",
            source="behaviors/order-placed-v2.md",
            title="Placing an order",
            state=State.SPECIFIED,
            supersedes=("behavior:order-placed",),
            trigger="The customer confirms a basket.",
            observations=(
                Observation(
                    id="behavior:order-placed-v2#obs-1",
                    statement="The order appears in the order cache",
                    at="resource:order-cache",
                    outcome=Outcome.MUST,
                    timing=Timing.IMMEDIATE,
                ),
                Observation(
                    id="behavior:order-placed-v2#obs-2",
                    statement="No order is cached before the payment clears",
                    at="resource:order-cache",
                    outcome=Outcome.MUST_NOT,
                ),
            ),
        ),
        "behaviors/order-placed-v2.md",
    ),
    "components": (
        Component(
            id="component:cancellation",
            source="components/cancellation.md",
            title="Cancellation",
            level=ComponentLevel.COMPONENT,
            responsibility="Decide whether an order may still be cancelled",
            technology="Python 3.14",
            parent="component:orders",
            implemented_by=("acme#src/orders/cancel.py",),
        ),
        "components/cancellation.md",
    ),
    "interfaces": (
        Interface(
            id="interface:order-events",
            source="interfaces/order-events.md",
            title="Order events",
            style=InterfaceStyle.EVENT,
            declared_by="component:orders",
            contract="docs/order-events.md",
            operations=(
                Operation(
                    name="order-cancelled",
                    signature="OrderCancelled { order_id: str, at: datetime }",
                    idempotent=True,
                    errors=("the bus is unreachable",),
                ),
            ),
            implemented_by=("acme#src/orders/events.py",),
            failure_modes=("The bus is unreachable and the event is dropped.",),
        ),
        "interfaces/order-events.md",
    ),
    "data_entities": (
        DataEntity(
            id="data:order",
            source="data_entities/order.md",
            title="Order",
            owner_component="component:orders",
            fields=(
                FieldSpec(name="id", type="uuid"),
                FieldSpec(name="state", type="str", optional=True, note="placed, cancelled"),
            ),
            identity=("id",),
        ),
        "data_entities/order.md",
    ),
    "resources": (
        Resource(
            id="resource:order-cache",
            source="resources/order-cache.md",
            title="Order cache",
            state=State.SPECIFIED,
            resource_kind=ResourceKind.STORE,
            technology="Redis",
        ),
        "resources/order-cache.md",
    ),
    "libraries": (
        Library(
            id="library:pydantic",
            source="libraries/pydantic.md",
            title="pydantic",
            package="pydantic",
            ecosystem="pypi",
            version_range=">=2.13",
            license="MIT",
            replaceable=False,
        ),
        "libraries/pydantic.md",
    ),
    "external_services": (
        ExternalService(
            id="external:stripe",
            source="external_services/stripe.md",
            title="Stripe",
            technology="REST/JSON",
            contract="https://example.invalid/stripe/openapi.yaml",
            assumptions=("Idempotency keys are honoured.",),
            failure_modes=("A settled charge is reported as pending.",),
            verified_on=date(2026, 1, 10),
            expires_on=date(2026, 7, 10),
        ),
        "external_services/stripe.md",
    ),
    "assumptions": (
        Assumption(
            id="assumption:refunds-settle",
            source="assumptions/refunds-settle.md",
            title="Refunds settle overnight",
            statement="A refund settles within one business day.",
            verified_on=date(2026, 1, 10),
            expires_on=date(2026, 7, 10),
            invalidates=("req:cancel-orders",),
        ),
        "assumptions/refunds-settle.md",
    ),
    "decisions": (
        Decision(
            id="decision:event-log",
            source="decisions/event-log.md",
            title="Orders publish an event log",
            reversibility=Reversibility.ONE_WAY,
            tags=("arch",),
            context="Cancellation and the catalog both need to know an order moved.",
            choice="Orders publishes every state change as an event.",
            consequences=("A reader can be added without touching Orders.",),
            alternatives=("A shared table, which makes every reader a writer's problem.",),
            applies_to=("component:orders",),
            decided_on=date(2026, 1, 15),
            body="## Context\n\nThe audit trail is the product.\n\n## Consequences\n\nReaders project.",
        ),
        "decisions/event-log.md",
    ),
    "questions": (
        Question(
            id="question:refund-window",
            source="questions/refund-window.md",
            title="How long is the refund window?",
            question="How long after a purchase may a customer still claim a refund?",
            method=ResolutionMethod.MEASURE,
            blocks=("milestone:m1",),
            resolved_by="decision:event-log",
        ),
        "questions/refund-window.md",
    ),
    "rejections": (
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
    "milestones": (
        Milestone(
            id="milestone:m1",
            source="milestones/m1.md",
            title="Cancellation",
            outcome="A customer can cancel an order that has not shipped.",
            includes=("behavior:order-placed-v2",),
            scope=("component:cancellation",),
            must_hold=("decision:event-log",),
            may_decide=("The retry policy behind publishing the event.",),
            unresolved=("question:refund-window",),
            done_when=("behavior:order-placed-v2#obs-1",),
        ),
        "milestones/m1.md",
    ),
    "notes": (
        Note(
            id="note:a1b2c3",
            created_on=date(2026, 8, 16),
            text="Ask ops whether anybody actually opens the shadow report.",
            about=("component:cancellation",),
            done_on=date(2026, 8, 20),
            promoted_to="question:refund-window",
        ),
        "notes/a1b2c3.md",
    ),
}

# Singletons are plain YAML — `layout.yaml`, a repo `.absicht` marker: no
# front matter, no body split, but the same round-trip promise. `design.yaml`
# is one too, and gets its own test because it is written by `dump_design`.
SINGLETONS: dict[str, tuple[Record, type[Record]]] = {
    "layout": (
        Layout(positions=(Position(ref="component:orders", x=120.0, y=-40.5),)),
        Layout,
    ),
    "marker": (
        Marker(
            design="/srv/design",
            units=(
                Watermark(
                    id="component:orders",
                    path="src/orders",
                    at="milestone:m1",
                    design_rev="abc123",
                ),
            ),
        ),
        Marker,
    ),
}


def test_every_directory_the_store_holds_has_a_round_trip_case() -> None:
    """`DIRECTORIES` is the whole on-disk layout, so a kind missing here is a
    directory nothing has ever been read back out of."""

    assert tuple(ELEMENTS) == tuple(DIRECTORIES)


@pytest.mark.parametrize(("record", "path"), ELEMENTS.values(), ids=list(ELEMENTS))
def test_each_kind_survives_a_round_trip(record: Element | Note, path: str) -> None:
    assert parse_element(dump_element(record), model=type(record), source=path) == (record, ())


@pytest.mark.parametrize(("record", "model"), SINGLETONS.values(), ids=list(SINGLETONS))
def test_singletons_survive_a_round_trip_as_plain_yaml(record: Record, model: type[Record]) -> None:
    assert parse_singleton(dump_singleton(record), model=model) == record


def test_a_behaviors_observations_serialize_inline_under_observations() -> None:
    """The codec needs no behavior-specific code: it is generic over pydantic
    models, so observations ride in the front matter as a nested record list
    under the model's own field name. The on-disk spelling stays the format
    contract rather than a codec special case."""

    (behavior, path) = ELEMENTS["behaviors"]

    text = dump_element(behavior)

    assert "observations:" in text
    assert "behavior:order-placed-v2#obs-2" in text
    assert parse_element(text, model=Behavior, source=path) == (behavior, ())


# ------------------------------------------------------------- relationships


def test_an_elements_edges_round_trip_through_its_own_relates_block() -> None:
    """The model keeps every edge in one list on the `Design` so two elements
    cannot disagree about a link; the store keeps each edge beside the element
    that owns it so one edit touches one file. This is the translation, and it
    is lossless in both directions — label and technology included."""

    (component, path) = ELEMENTS["components"]
    edges = (
        Relationship(
            source_id=component.id,
            target_id="interface:order-events",
            type=RelationshipType.CALLS,
            description="publishes the cancellation",
            technology="JSON over the event bus",
        ),
        Relationship(
            source_id=component.id,
            target_id="quality:cancel-latency",
            type=RelationshipType.SATISFIES,
        ),
    )

    text = dump_element(component, relates=edges)

    assert "relates:" in text
    assert parse_element(text, model=Component, source=path) == (component, edges)


def test_an_element_with_no_edges_writes_no_relates_key() -> None:
    """A key spelled `relates: []` in every file is noise in every diff, and
    an empty block says nothing the missing block does not."""

    (component, _) = ELEMENTS["components"]

    assert "relates" not in dump_element(component)


def test_an_edge_may_not_name_its_own_source() -> None:
    """The file an edge is written in is its source. Spelling it a second
    time is how the two come to disagree, so the key is simply not there."""

    with pytest.raises(CodecValidationError, match="source_id"):
        parse_element(
            _component_text(
                "relates:\n"
                "- to: interface:order-events\n"
                "  type: calls\n"
                "  source_id: component:somebody-else\n"
            ),
            model=Component,
            source="components/x.md",
        )


@pytest.mark.parametrize(
    ("relates", "match"),
    [
        ("relates: not-a-list\n", "must be a list"),
        ("relates:\n- just a string\n", "must be a mapping"),
    ],
    ids=["not-a-list", "entry-not-a-mapping"],
)
def test_a_malformed_relates_block_is_a_syntax_error(relates: str, match: str) -> None:
    with pytest.raises(CodecSyntaxError, match=match):
        parse_element(_component_text(relates), model=Component, source="components/x.md")


def test_an_edge_of_an_unknown_type_is_a_validation_error() -> None:
    """A checker branches on the edge kind, so an invented one is a file that
    nothing downstream could act on — refused where the file is read."""

    with pytest.raises(CodecValidationError, match=r"validation failed: type\b"):
        parse_element(
            _component_text("relates:\n- to: component:orders\n  type: knows_about\n"),
            model=Component,
            source="components/x.md",
        )


def test_only_an_element_may_carry_relates() -> None:
    """A note is not in the graph and has nothing to point at with an edge, so
    the reserved key is not reserved on its file: pydantic sees an unknown key
    and refuses it, which is the report we want."""

    text = (
        "---\nid: note:a1b2c3\ncreated_on: 2026-08-16\n"
        "relates:\n- to: component:orders\n  type: relates_to\n---\n"
    )

    with pytest.raises(CodecValidationError, match="relates"):
        parse_element(text, model=Note, source="notes/a1b2c3.md")


def test_an_element_document_schema_admits_the_key_the_model_forbids() -> None:
    """An editor validating a file has to be told about `relates`, or every
    authored edge reads as an error — while the model itself must keep
    refusing it, because an assembled edge lives on the `Design`."""

    assert "relates" in _properties(document_schema(Component))
    assert "relates" not in _properties(document_schema(Note))
    with pytest.raises(ValidationError, match="relates"):
        Component.model_validate(
            {"id": "component:x", "title": "X", "level": "container", "relates": []}
        )


# ---------------------------------------------------------------- provenance


def test_the_source_is_stamped_from_the_path_and_never_read_from_the_file() -> None:
    """Provenance is the loader's to write. A file that states its own path is
    stating where it was last copied from, and `check` reports on where the
    file actually is."""

    record, _ = parse_element(
        "---\nid: component:x\ntitle: X\nlevel: container\nsource: somewhere/else.md\n---\n",
        model=Component,
        source="components/x.md",
    )

    assert record.source == "components/x.md"
    assert "source" not in dump_element(record)


def test_a_notes_body_is_its_text_because_that_is_all_a_note_is() -> None:
    """The body maps to `body` on an element and to `text` on a note, and a
    note takes no `source`: it is not addressed by anything, so nothing has to
    be told where it sits."""

    note, edges = parse_element(
        "---\nid: note:a1b2c3\ncreated_on: 2026-08-16\n---\nAsk ops about this.\n",
        model=Note,
        source="notes/a1b2c3.md",
    )

    assert note.text == "Ask ops about this."
    assert edges == ()
    assert "source" not in Note.model_fields


# -------------------------------------------------------------- design.yaml


def test_design_yaml_holds_the_header_and_never_the_store() -> None:
    """Everything in `ASSEMBLED` is many files on disk. Writing it into the
    header too would be a second copy, and it would drift on the first edit —
    so the round trip is header in, header out."""

    design = Design(
        id="design:acme",
        title="ACME orders",
        version="1.0.0",
        purpose="Sell things, honestly.",
        exports=("interface:order-events",),
        components=(Component(id="component:orders", title="Orders", level=ComponentLevel.SYSTEM),),
        relationships=(
            Relationship(
                source_id="component:orders",
                target_id="req:cancel-orders",
                type=RelationshipType.IMPLEMENTS,
            ),
        ),
    )

    text = dump_design(design)

    for field in ASSEMBLED:
        assert f"{field}:" not in text
    assert parse_singleton(text, model=Design) == design.model_copy(
        update=dict.fromkeys(ASSEMBLED, ())
    )


# ------------------------------------------------------------------- errors


def test_front_matter_without_a_body_parses_to_an_empty_body() -> None:
    record, _ = parse_element(_component_text(), model=Component, source="components/x.md")

    assert record.body == ""


def test_a_body_without_front_matter_is_refused() -> None:
    """Prose alone is not an element: `id` and `title` live in the front matter."""

    with pytest.raises(CodecError, match="front matter"):
        parse_element("Just prose, no delimiters.\n", model=Component, source="components/x.md")


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(CodecError, match="front matter"):
        parse_element("", model=Component, source="components/x.md")


def test_empty_front_matter_reports_the_missing_fields() -> None:
    """`---\\n---\\n` is well-shaped but contentless: the error must name what is absent."""

    with pytest.raises(CodecError, match=r"\bid\b"):
        parse_element("---\n---\n", model=Component, source="components/x.md")


def test_unterminated_front_matter_is_refused() -> None:
    with pytest.raises(CodecError, match="unterminated"):
        parse_element("---\nid: component:x\n", model=Component, source="components/x.md")


def test_the_first_delimiter_pair_wins_and_a_body_may_hold_its_own_rules() -> None:
    """A Markdown body is prose, and prose contains horizontal rules. The
    front matter is what the first pair encloses; everything after is body,
    verbatim."""

    record, _ = parse_element(
        "---\nid: component:x\ntitle: X\nlevel: container\n---\nAbove.\n\n---\n\nBelow.\n",
        model=Component,
        source="components/x.md",
    )

    assert record.body == "Above.\n\n---\n\nBelow."


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
            "---\nid: not-a-ref\ntitle: X\nlevel: container\n---\n",
            model=Component,
            source="components/x.md",
        )


def test_the_two_failure_families_raise_their_own_subclass() -> None:
    """`check` maps each family to its own rule id (`store/yaml-syntax` vs
    `store/validation`), so the family is told apart here — at the boundary
    that raises — and never guessed from a message one layer up."""

    with pytest.raises(CodecSyntaxError, match="invalid YAML"):
        parse_element("---\nid: [unclosed\n---\n", model=Component, source="components/x.md")
    with pytest.raises(CodecSyntaxError, match="front matter"):
        parse_element("no delimiters at all\n", model=Component, source="components/x.md")
    with pytest.raises(CodecValidationError, match=r"validation failed: id\b"):
        parse_element(
            "---\nid: not-a-ref\ntitle: X\nlevel: container\n---\n",
            model=Component,
            source="components/x.md",
        )


def test_singleton_errors_are_translated_too() -> None:
    with pytest.raises(CodecError, match="invalid YAML"):
        parse_singleton("imports: [unclosed", model=Design)
    with pytest.raises(CodecError, match="mapping"):
        parse_singleton("- just\n- a\n- list", model=Design)
    with pytest.raises(CodecError, match=r"validation failed: title\b"):
        parse_singleton("id: design:acme", model=Design)


def test_field_order_is_declaration_order_regardless_of_construction() -> None:
    """Diffs stay small only if equal elements always dump to equal text."""

    by_kwargs = Component(
        implemented_by=("acme#src/billing",),
        level=ComponentLevel.CONTAINER,
        title="Billing",
        id="component:billing",
    )
    by_reversed_dict = Component.model_validate(
        {
            "implemented_by": ["acme#src/billing"],
            "level": "container",
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


def _component_text(extra: str = "") -> str:
    return f"---\nid: component:x\ntitle: X\nlevel: container\n{extra}---\n"


def _properties(schema: dict[str, object]) -> dict[str, object]:
    properties = schema["properties"]
    assert isinstance(properties, dict)
    return properties
