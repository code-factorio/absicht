"""``ab check``'s first layer: schema findings — fields, types, patterns.

The layer with the least new logic to write: pydantic already enforced the
field types and the ``Ref``/``Slug``/``CriterionId`` patterns at parse time,
inside ``absicht.codec``/``absicht.load``, and every file that failed there is
already a ``LoadError``. What this module adds is the translation ``load``
deliberately does not do — one ``LoadError`` becomes one ``Finding`` at error
severity, under a rule id that says which *kind* of schema problem it was,
because ``ab check --explain ID`` answers "what does this rule check" per
rule, not per file.

The integrity and policy layers land in this same module (tasks 13/14); the
CLI wiring — flags, formats, exit codes — is task 15's.
"""

from __future__ import annotations

from absicht.findings import RULES, Finding, Severity, finding
from absicht.load import LoadedStore, LoadErrorReason

RULES.update(
    {
        "schema/yaml-syntax": (
            "A file that is not the format: YAML the parser refuses, or a document "
            "without the --- front matter every element is read through. Always an "
            "error — a file that does not parse cannot be advisory."
        ),
        "schema/validation": (
            "A file that parsed but whose fields failed validation: a wrong type, a "
            "Ref/Slug/CriterionId pattern, or a record-level rule such as a criterion "
            "anchored to another story. The message names the offending field."
        ),
        "schema/system-missing": (
            "The store has no system.yaml. A store is exactly one System element plus "
            "its kind directories, and everything downstream reads the system."
        ),
        "schema/unreadable-file": (
            "A file the loader could not read at all — permissions, or it vanished "
            "mid-walk. Not a judgement about the design, but check cannot see past a "
            "file it cannot read."
        ),
    }
)

_RULE_BY_REASON: dict[LoadErrorReason, str] = {
    LoadErrorReason.SYNTAX: "schema/yaml-syntax",
    LoadErrorReason.VALIDATION: "schema/validation",
    LoadErrorReason.MISSING_SYSTEM: "schema/system-missing",
    LoadErrorReason.IO: "schema/unreadable-file",
}
"""One rule id per failure family — the reason exists so this is a lookup, not message parsing."""


def schema_findings(loaded: LoadedStore) -> tuple[Finding, ...]:
    """One error-severity finding per ``LoadError``, in the order load reported them."""
    return tuple(
        finding(
            _RULE_BY_REASON[error.reason],
            severity=Severity.ERROR,
            message=error.message,
            source=error.path,
        )
        for error in loaded.errors
    )
