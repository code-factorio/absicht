"""The records, split by what reads them.

`design` is the design itself, and everything else in the package points at
it: `packet` is the slice an agent is handed, `layout` where a diagram draws
each box, `marker` what an implementing repository knows about the store.

Nothing is re-exported here. A module names which of the four it needs, so a
reader of an import list already knows whether it is looking at design data,
a hand-off, or a rendering detail.
"""
