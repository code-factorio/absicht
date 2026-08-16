"""The command surface, checked against `docs/spec/cli.md`.

The surface *is* the deliverable at this point — the bodies land step by step
behind it — so what these tests assert is the contract an agent or a CI job
codes against: the command exists, it takes the documented flags, and it exits
with a code that means something. `SURFACE` is the spec transcribed; a flag
renamed in the code and not in the doc fails here.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import pytest
import typer
from typer.testing import CliRunner

from absicht import __version__
from absicht.cli import app, author, handoff, query, reconcile
from absicht.cli._common import ExitCode, GlobalOptions, options
from absicht.models import SCHEMA_VERSION

runner = CliRunner()

# One entry per documented command: the argv that reaches it, and every flag the
# spec lists for it. The positional arguments are placeholders — a command that
# has no body yet never looks at them.
SURFACE: dict[str, tuple[list[str], list[str]]] = {
    "init": (["init"], ["--embedded", "--reference", "--name", "--force"]),
    "new": (
        ["new", "component", "some-slug"],
        ["--title", "--state", "--owner", "--edit", "--print"],
    ),
    "check": (
        ["check"],
        [
            "--rule",
            "-r",
            "--exclude-rule",
            "--severity",
            "--strict",
            "--changed-only",
            "--diff-base",
            "--format",
            "--explain",
        ],
    ),
    "schema": (["schema"], ["--out", "--check"]),
    "migrate": (["migrate"], ["--to", "--dry-run"]),
    "build": (["build"], ["--out", "--stdout", "--check"]),
    "show": (["show", "component:x"], ["--format", "--depth", "--body", "--no-body"]),
    "list": (
        ["list", "component"],
        [
            "--state",
            "--confidence",
            "--owner",
            "--unowned",
            "--tag",
            "--milestone",
            "--orphaned",
            "--format",
        ],
    ),
    "gaps": (["gaps"], ["--kind", "--owner", "--overdue", "--blocking", "--format"]),
    "trace": (["trace", "component:x"], ["--to", "--up", "--down", "--format"]),
    "render": (
        ["render"],
        ["--out", "--serve", "--port", "--overlay", "--format", "--scope"],
    ),
    "layout": (["layout"], ["--recompute", "--recompute-all", "--seed", "--check"]),
    "packet": (
        ["packet", "milestone:m1"],
        [
            "--out",
            "--stdout",
            "--format",
            "--horizon",
            "--include",
            "--exclude",
            "--features",
            "--no-features",
            "--features-dir",
            "--rev",
            "--seal",
        ],
    ),
    "features": (["features", "milestone:m1"], ["--out", "--stdout", "--check"]),
    "verify": (
        ["verify"],
        [
            "--packet",
            "--repo",
            "--diff-base",
            "--rule",
            "--exclude-rule",
            "--strict",
            "--format",
            "--report",
        ],
    ),
    "status": (
        ["status"],
        ["--repo", "--unit", "--behind-only", "--since", "--fail-on-drift", "--format"],
    ),
    "diff": (["diff", "HEAD~1", "HEAD"], ["--scope", "--kind", "--format"]),
    "marker sync": (["marker", "sync", "--repo", "."], ["--repo"]),
    "marker check": (["marker", "check", "--repo", "."], ["--repo"]),
    "marker stamp": (
        ["marker", "stamp", "--repo", ".", "--unit", "component:x", "--milestone", "milestone:m1"],
        ["--repo", "--unit", "--milestone"],
    ),
}

# Rich wraps help text to the console width, which would split a long flag name
# across lines and make a substring search lie.
WIDE = {"COLUMNS": "200"}

# Commands whose bodies have landed. The two parametrizations that assume a
# bodyless command — exiting INTERNAL through `unimplemented`, and recording
# the globals through the `seen` fixture's monkeypatched `unimplemented` —
# skip them here; a landed command covers the same ground against its real
# behaviour in its own test module (the `--json` fold included, per
# docs/adr/0001). The flag-presence test stays over the whole surface.
IMPLEMENTED = {"init", "migrate", "schema"}
NOT_IMPLEMENTED = [name for name in SURFACE if name not in IMPLEMENTED]


@pytest.mark.parametrize(("name", "flags"), [(n, f) for n, (_, f) in SURFACE.items()])
def test_command_offers_every_documented_flag(name: str, flags: list[str]) -> None:
    argv, _ = SURFACE[name]

    result = runner.invoke(app, [*argv, "--help"], env=WIDE)

    assert result.exit_code == ExitCode.OK
    missing = [flag for flag in flags if flag not in result.output]
    assert not missing, f"`ab {name}` is missing {missing}"


@pytest.mark.parametrize(
    "argv", [SURFACE[name][0] for name in NOT_IMPLEMENTED], ids=NOT_IMPLEMENTED
)
def test_command_parses_its_arguments_and_reports_no_body_yet(argv: list[str]) -> None:
    """Every command parses its arguments and says what it is, rather than crashing.

    `INTERNAL` distinguishes "not built yet" from the `USAGE` a bad flag earns,
    so a caller wiring this up early can tell the two apart. Nothing lands on
    stdout, because an empty result there is a parseable one.
    """
    result = runner.invoke(app, argv)

    assert result.exit_code == ExitCode.INTERNAL
    assert "not implemented yet" in result.stderr
    assert result.stdout == ""


def test_version_reports_the_package_and_schema_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == ExitCode.OK
    assert result.output.strip() == f"absicht {__version__} (schema {SCHEMA_VERSION})"


def test_bare_invocation_prints_help_and_succeeds() -> None:
    """No subcommand is not an error: `ab` alone should be a usable way in."""
    result = runner.invoke(app, [])

    assert result.exit_code == ExitCode.OK
    assert "Absicht" in result.output


def test_an_unknown_flag_is_a_usage_error_not_a_finding() -> None:
    """CI reads 1 as a real result about the design and 2 as a broken pipeline."""
    result = runner.invoke(app, ["check", "--no-such-flag"])

    assert result.exit_code == ExitCode.USAGE


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> list[GlobalOptions]:
    """Capture what a command sees on its context instead of running it."""
    captured: list[GlobalOptions] = []

    def record(ctx: typer.Context) -> NoReturn:
        captured.append(options(ctx))
        raise typer.Exit()

    for module in (author, query, handoff, reconcile):
        monkeypatch.setattr(module, "unimplemented", record)
    return captured


def test_global_flags_reach_the_command(seen: list[GlobalOptions]) -> None:
    """Commands read the globals off the context rather than re-declaring them."""
    result = runner.invoke(app, ["--store", "elsewhere", "--rev", "v1", "--json", "-vv", "check"])

    assert result.exit_code == ExitCode.OK
    assert seen == [
        GlobalOptions(
            store=Path("elsewhere"),
            rev="v1",
            json_output=True,
            verbose=2,
            color=False,  # CliRunner's stdout is not a tty
        )
    ]


def test_the_store_falls_back_to_the_environment(seen: list[GlobalOptions]) -> None:
    result = runner.invoke(app, ["check"], env={"ABSICHT_STORE": "/srv/design"})

    assert result.exit_code == ExitCode.OK
    assert [o.store for o in seen] == [Path("/srv/design")]


@pytest.mark.parametrize(
    "argv", [SURFACE[name][0] for name in NOT_IMPLEMENTED], ids=NOT_IMPLEMENTED
)
def test_json_is_accepted_after_the_command_name(
    argv: list[str], seen: list[GlobalOptions]
) -> None:
    """`ab check --json`, not only `ab --json check`. See docs/adr/0001.

    Parametrized over the whole surface because the fold in `options` keys off
    the parameter name: a command that spells it differently would accept the
    flag and then quietly ignore it.
    """
    result = runner.invoke(app, [*argv, "--json"])

    assert result.exit_code == ExitCode.OK
    assert [o.json_output for o in seen] == [True]


def test_json_means_the_same_thing_on_either_side_of_the_command(
    seen: list[GlobalOptions],
) -> None:
    """Both positions, and both at once, are one boolean — not a shadowed pair."""
    for argv in (["--json", "check"], ["check", "--json"], ["--json", "check", "--json"]):
        runner.invoke(app, argv)

    assert [o.json_output for o in seen] == [True, True, True]
