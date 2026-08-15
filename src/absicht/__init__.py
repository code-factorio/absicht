"""Absicht — the design store.

The component of Code Factorio that holds why a system is shaped the way it
is: what it must not do, what was deliberately left open, and who is allowed
to decide the rest. Structure is derivable from code. Intent is not.

The unit of output is the packet: a bounded, machine-readable brief for one
slice of work, assembled by walking the model.

This package is a library first. The CLI in ``absicht.cli`` is a shell around
it and holds no logic of its own. Vocabulary is defined in ``CONTEXT.md``.
"""

__version__ = "0.1.0"
