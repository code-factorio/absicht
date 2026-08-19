"""The designer's interface: a local web view of the design store.

The CLI is the agent surface. This is the human one — ``actor:designer`` rather
than ``actor:agent`` — and the two are separate on purpose: an agent wants
``--json`` on a pipe, a designer wants a map they can navigate.

It is a *view*. Every answer on a page comes from the same library the CLI
calls, so the two surfaces cannot tell different stories about one store.

FastAPI and uvicorn are the ``ui`` extra rather than runtime dependencies:
importing this package must stay free for a core install, because the agent
half of the tool should not pay for a server it never starts.
"""

from __future__ import annotations

from absicht.ui._server import (
    DEFAULT_PORT,
    EXTRA_HINT,
    LOCALHOST,
    MissingExtraError,
    create_app,
    serve,
)

__all__ = [
    "DEFAULT_PORT",
    "EXTRA_HINT",
    "LOCALHOST",
    "MissingExtraError",
    "create_app",
    "serve",
]
