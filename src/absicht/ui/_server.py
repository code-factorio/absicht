"""The HTTP surface behind ``ab ui``.

Two rules shape this module.

The extra is optional, so ``fastapi`` and ``uvicorn`` are imported inside the
functions that need them. A core install must be able to import
:mod:`absicht.ui` and get a clear refusal, not an ``ImportError`` traceback
from three frames down.

Nothing is cached. Every request rebuilds from the store, because the designer
and the agent both edit it while the page is open, and a stale map is worse
than a slow one. The store is small and the fold is deterministic; when that
stops being true, the fix is a watcher, not a cache with no invalidation.
"""

# FastAPI registers routes through decorators.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from absicht.build import build as build_design
from absicht.models.design import Design
from absicht.resolve import COLLECTIONS

if TYPE_CHECKING:
    from fastapi import FastAPI

EXTRA_HINT = "ab ui needs the 'ui' extra — install it with: uv add 'absicht[ui]'"

LOCALHOST = "127.0.0.1"
"""The default bind address. A design store is not something to publish."""

DEFAULT_PORT = 8765


class MissingExtraError(RuntimeError):
    """``fastapi`` or ``uvicorn`` is absent, so the ``ui`` extra was not installed."""

    def __init__(self) -> None:
        super().__init__(EXTRA_HINT)


def create_app(root: Path, *, rev: str | None = None) -> FastAPI:
    """The application object, built but not served.

    Returned rather than run so tests can drive the routes over an in-process
    transport instead of a socket.
    """
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised without the extra
        raise MissingExtraError from exc

    # The OpenAPI pages are for machine consumers, and the machine consumer of
    # absicht is the CLI. Off, so the surface is exactly the pages a designer
    # can reach.
    app = FastAPI(title="absicht", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return index_page(build_design(root, rev=rev))

    return app


def serve(
    root: Path,
    *,
    host: str = LOCALHOST,
    port: int = DEFAULT_PORT,
    rev: str | None = None,
) -> None:
    """Run the interface until interrupted."""
    try:
        import uvicorn
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised without the extra
        raise MissingExtraError from exc

    uvicorn.run(create_app(root, rev=rev), host=host, port=port, log_level="warning")


def counts(design: Design) -> list[tuple[str, int]]:
    """How many records of each kind the store holds, empty kinds dropped.

    Reads :data:`absicht.resolve.COLLECTIONS` rather than listing the kinds
    again: a new element kind should appear here by existing, not by someone
    remembering this module.
    """
    found: list[tuple[str, int]] = []
    for name in COLLECTIONS:
        records = getattr(design, name, ())
        if records:
            found.append((name.replace("_", " "), len(records)))
    return found


def index_page(design: Design) -> str:
    """The landing page: what this store is, and what is in it."""
    rows = "".join(
        f"<tr><td>{escape(kind)}</td><td class='n'>{total}</td></tr>"
        for kind, total in counts(design)
    )
    body = (
        f"<h1>{escape(design.title)}</h1>"
        f"<p class='meta'><code>{escape(design.id)}</code> · version {escape(design.version)}</p>"
        f"<p>{escape(design.purpose)}</p>"
        f"<table><thead><tr><th>kind</th><th class='n'>count</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
    return page(design.title, body)


def page(title: str, body: str) -> str:
    """The document every page shares.

    The palette is the one the diagrams already use, so a node keeps its colour
    when the designer looks away from the map and back again.
    """
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title>"
        f"<style>{_STYLE}</style>"
        "</head><body><main>"
        f"{body}"
        "</main></body></html>"
    )


_STYLE = """
:root { --surface:#fcfcfb; --frame:#c3c2b7; --ink:#1a1a1a; --muted:#6b6a63; }
* { box-sizing:border-box; }
body { margin:0; background:var(--surface); color:var(--ink);
       font:15px/1.55 ui-sans-serif, system-ui, sans-serif; }
main { max-width:52rem; margin:0 auto; padding:2.5rem 1.5rem; }
h1 { font-size:1.6rem; margin:0 0 .25rem; }
.meta { color:var(--muted); margin:0 0 1.25rem; }
code { font:13px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; }
table { border-collapse:collapse; width:100%; margin-top:1.5rem; }
th, td { text-align:left; padding:.4rem .6rem; border-bottom:1px solid var(--frame); }
th { font-weight:600; font-size:.8rem; text-transform:uppercase;
     letter-spacing:.04em; color:var(--muted); }
.n { text-align:right; font-variant-numeric:tabular-nums; }
"""
