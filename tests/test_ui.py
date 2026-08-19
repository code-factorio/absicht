"""The designer's interface.

The page is a view, so what is worth asserting is that it tells the truth about
the store and that design prose cannot become markup. The look of it is not
pinned here — that is what makes the HTML free to change.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from absicht.load import load_store
from absicht.models.design import Design
from absicht.resolve import resolve
from absicht.ui import create_app
from absicht.ui._server import counts, index_page

FIXTURES = Path(__file__).parent / "fixtures" / "systems"


@pytest.fixture
def clean() -> Design:
    return resolve(load_store(FIXTURES / "clean"))


def test_counts_reports_what_the_store_holds(clean: Design) -> None:
    reported = dict(counts(clean))

    assert reported["components"] == len(clean.components)
    assert reported["requirements"] == len(clean.requirements)


def test_counts_leaves_out_the_kinds_nobody_authored(clean: Design) -> None:
    """An empty kind is not a row. A design that uses six of the twenty-three
    kinds should read as six lines, not seventeen zeroes."""
    empty = {name for name, total in counts(clean) if total == 0}

    assert not empty


def test_prose_cannot_become_markup(clean: Design) -> None:
    """Titles and bodies are authored text. The store is a trusted source
    today, but it is also written by an agent through a chat box, so the page
    escapes rather than trusting."""
    hostile = clean.model_copy(update={"title": "<script>alert(1)</script>"})

    rendered = index_page(hostile)

    assert "<script>alert(1)</script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_the_index_serves_the_design_it_was_pointed_at() -> None:
    client = TestClient(create_app(FIXTURES / "clean"))

    response = client.get("/")

    assert response.status_code == 200
    assert resolve(load_store(FIXTURES / "clean")).title in response.text


def test_every_request_re_reads_the_store(tmp_path: Path) -> None:
    """The designer edits underneath an open page, so a second request must see
    the change. Nothing is cached between requests."""
    store = tmp_path / ".absicht"
    store.mkdir()
    design_yaml = FIXTURES / "clean" / "design.yaml"
    for source in (FIXTURES / "clean").rglob("*"):
        target = store / source.relative_to(FIXTURES / "clean")
        if source.is_dir():
            target.mkdir(exist_ok=True)
        else:
            target.write_bytes(source.read_bytes())
    client = TestClient(create_app(store))

    before = client.get("/").text
    (store / "design.yaml").write_text(
        design_yaml.read_text(encoding="utf-8").replace("title: ", "title: Renamed ", 1),
        encoding="utf-8",
    )
    after = client.get("/").text

    assert "Renamed" in after
    assert before != after
