"""The designer's interface: a local web view of the design store.

The CLI is the agent surface. This is the human one — ``actor:designer`` rather
than ``actor:agent`` — and the two are separate on purpose: an agent wants
``--json`` on a pipe, a designer wants a map they can navigate.

It is a *view*. Every answer on a page comes from the same library the CLI
calls, so the two surfaces cannot tell different stories about one store.

``fastapi`` and ``uvicorn`` are the ``ui`` extra rather than runtime
dependencies, so importing this package needs them: the CLI reaches it from
inside ``ab ui`` rather than at start-up.
"""

from __future__ import annotations

from absicht.ui._server import create_app, serve

__all__ = ["create_app", "serve"]
