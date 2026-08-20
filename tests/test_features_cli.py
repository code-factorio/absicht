"""``ab features MILESTONE``: the Gherkin slice of the packet, on its own.

The rendering itself is ``tests/test_gherkin.py``'s and the behavior walk is
``tests/test_packet.py``'s; here it is the command around them:

- the files written for ``clean/``'s milestone are the renderer's own output
  for the same behaviors — the bytes ``test_gherkin.py`` pins whole — which is
  the entire claim of the command: it wires the renderer to the milestone's
  behaviors, nothing more, and names each file by the behavior's slug because
  those names are what ``ab packet --seal`` digests;
- ``--stdout`` prints the files instead of writing them, each under a ``#``
  header naming where it would have landed: a Gherkin comment, so the stream
  stays parseable while an agent can still tell where one file ends and the
  next begins;
- ``--check`` is the guardrail behind "output is generated, never authored":
  a hand-edited file, a file that was never written and a file nothing renders
  any more are all drift — ``FINDINGS``, naming the file — while non-Gherkin
  files beside them (step definitions) are none of its business;
- the refusals are ``ab packet``'s own: an unknown milestone is ``USAGE``, a
  milestone that names no scope is ``FINDINGS`` — these are the files a packet
  seals, so the same milestones qualify for both commands.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from absicht.cli import app
from absicht.cli._common import ExitCode
from absicht.gherkin import render_feature
from absicht.load import load_store
from absicht.models.design import FORMAT_VERSION, Behavior
from absicht.resolve import Index, resolve

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures" / "systems"
CLEAN = FIXTURES / "clean"
FEATURE = "order-cancelled.feature"


def _features(*flags: str, store: Path = CLEAN, milestone: str = "milestone:m1") -> Any:
    return runner.invoke(app, ["--store", str(store), "features", milestone, *flags])


def _expected_feature() -> str:
    """The rendering computed independently of the CLI: the fixture's behavior
    through the same renderer whose output ``tests/test_gherkin.py`` pins."""
    index = Index(resolve(load_store(CLEAN)))
    behavior = index.get("behavior:order-cancelled")
    assert isinstance(behavior, Behavior)
    return render_feature(behavior, index)


@contextmanager
def _cwd(directory: Path) -> Iterator[Path]:
    """Run with the cwd moved into a directory the test owns, so a relative
    default ``--out`` lands there — typer's CliRunner has no isolated
    filesystem of its own."""
    directory.mkdir(parents=True, exist_ok=True)
    origin = Path.cwd()
    os.chdir(directory)
    try:
        yield directory
    finally:
        os.chdir(origin)


@pytest.fixture
def unscoped(tmp_path: Path) -> Path:
    """A copy of ``clean/`` carrying one milestone that names no scope.

    ``broken/``'s own ``milestone:unscoped`` cannot serve here: three of that
    fixture's files fail to load on purpose, and the command refuses a store it
    cannot read whole long before it reaches assembly."""
    store = tmp_path / "store"
    shutil.copytree(CLEAN, store)
    (store / "milestones" / "unscoped.md").write_text(
        "---\n"
        "id: milestone:unscoped\n"
        "title: Unscoped\n"
        "state: specified\n"
        "outcome: Something gets better.\n"
        "---\n",
        encoding="utf-8",
    )
    return store


# -------------------------------------------------------------------- writing


def test_the_written_file_is_the_renderers_own_output(tmp_path: Path) -> None:
    out = tmp_path / "features"

    result = _features("--out", str(out))

    assert result.exit_code == ExitCode.OK
    assert (out / FEATURE).read_text(encoding="utf-8") == _expected_feature()
    assert result.stdout == f"wrote {out} (1 feature file)\n"


def test_the_file_is_named_by_the_behavior_slug(tmp_path: Path) -> None:
    """The name ``ab packet --seal`` folds into its digest, so the two commands
    must spell it identically: the behavior's slug, not the milestone's and not
    the whole ``behavior:`` id."""
    out = tmp_path / "features"

    assert _features("--out", str(out)).exit_code == ExitCode.OK

    assert {path.name for path in out.iterdir()} == {FEATURE}


def test_the_default_out_is_features_under_the_cwd(tmp_path: Path) -> None:
    with _cwd(tmp_path) as cwd:
        result = _features()

    assert result.exit_code == ExitCode.OK
    assert (cwd / "features" / FEATURE).is_file()


def test_stdout_prints_the_files_and_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "features"

    result = _features("--out", str(out), "--stdout")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == f"# {out / FEATURE}\n{_expected_feature()}"
    assert not out.exists()


# ------------------------------------------------------------------- checking


def test_check_passes_when_the_disk_matches(tmp_path: Path) -> None:
    out = tmp_path / "features"
    assert _features("--out", str(out)).exit_code == ExitCode.OK

    result = _features("--out", str(out), "--check")

    assert result.exit_code == ExitCode.OK
    assert result.stdout == f"{out} is up to date\n"


def test_check_names_a_hand_edited_file(tmp_path: Path) -> None:
    """The guardrail "an agent implements step definitions and may not touch
    these files" hangs on: one edited step line is drift, named, with the exit
    code a CI gate reads."""
    out = tmp_path / "features"
    assert _features("--out", str(out)).exit_code == ExitCode.OK
    path = out / FEATURE
    hand_edited = path.read_text(encoding="utf-8").replace(
        "Then The order reads cancelled.", "Then The order reads refunded."
    )
    path.write_text(hand_edited, encoding="utf-8")

    result = _features("--out", str(out), "--check")

    assert result.exit_code == ExitCode.FINDINGS
    assert f"stale: {path} differs from a fresh render" in result.stdout
    assert f"run ab features milestone:m1 --out {out} to refresh" in result.stdout
    # Checking never writes: the hand edit is what the next run sees too.
    assert path.read_text(encoding="utf-8") == hand_edited


def test_check_names_a_file_that_was_never_written(tmp_path: Path) -> None:
    """A missing file has drifted from nothing. The alternative — `OK`
    because there was nothing to diff against — is the drift gate passing on
    exactly the case it exists to catch."""

    result = _features("--out", str(tmp_path / "features"), "--check")

    assert result.exit_code == ExitCode.FINDINGS
    assert (
        f"stale: {tmp_path / 'features' / FEATURE} is rendered but not on disk\n" in result.stdout
    )


def test_check_names_a_file_nothing_renders(tmp_path: Path) -> None:
    """A ``.feature`` file the command would not produce is drift too: these
    files are generated, never authored, so a hand-added one has no other
    legitimate way to be there."""
    out = tmp_path / "features"
    assert _features("--out", str(out)).exit_code == ExitCode.OK
    rogue = out / "rogue.feature"
    rogue.write_text("Feature: Rogue\n", encoding="utf-8")

    result = _features("--out", str(out), "--check")

    assert result.exit_code == ExitCode.FINDINGS
    assert f"stale: {rogue} is on disk but not rendered" in result.stdout


def test_check_ignores_files_that_are_not_gherkin(tmp_path: Path) -> None:
    """Step definitions live beside the features they drive; the drift gate
    guards the generated half only."""
    out = tmp_path / "features"
    assert _features("--out", str(out)).exit_code == ExitCode.OK
    (out / "steps.py").write_text("from pytest_bdd import parsers\n", encoding="utf-8")

    result = _features("--out", str(out), "--check")

    assert result.exit_code == ExitCode.OK


def test_json_envelopes_the_write_and_the_check(tmp_path: Path) -> None:
    out = tmp_path / "features"
    ahead = _features("--out", str(out), "--json")
    fresh = _features("--out", str(out), "--check", "--json")
    (out / FEATURE).write_text("Feature: Hand\n", encoding="utf-8")
    stale = _features("--out", str(out), "--check", "--json")

    assert ahead.exit_code == ExitCode.OK
    assert fresh.exit_code == ExitCode.OK
    assert stale.exit_code == ExitCode.FINDINGS
    assert json.loads(ahead.stdout) == {
        "format_version": FORMAT_VERSION,
        "out": str(out),
        "files": [FEATURE],
    }
    assert json.loads(fresh.stdout) == {
        "format_version": FORMAT_VERSION,
        "out": str(out),
        "stale": False,
        "files": [],
    }
    assert json.loads(stale.stdout) == {
        "format_version": FORMAT_VERSION,
        "out": str(out),
        "stale": True,
        "files": [FEATURE],
    }


def test_stdout_with_check_keeps_the_verdict_off_the_machine_output(tmp_path: Path) -> None:
    """``--stdout`` occupies stdout with the rendered files; the verdict is a
    diagnostic, so it moves to stderr rather than mixing into them."""
    out = tmp_path / "features"

    result = _features("--out", str(out), "--stdout", "--check")

    assert result.exit_code == ExitCode.FINDINGS
    assert result.stdout == f"# {out / FEATURE}\n{_expected_feature()}"
    assert "is rendered but not on disk" in result.stderr


# -------------------------------------------------------------- broken calls


def test_an_unknown_milestone_is_a_usage_error(tmp_path: Path) -> None:
    result = _features("--out", str(tmp_path / "out"), milestone="milestone:nope")

    assert result.exit_code == ExitCode.USAGE
    assert "milestone:nope" in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "out").exists()


def test_a_milestone_with_no_scope_is_findings(tmp_path: Path, unscoped: Path) -> None:
    """``ab features`` refuses what ``ab packet`` refuses — these are the files
    a packet seals, so the same milestones qualify for both. A true statement
    about the design (1), not a broken invocation (2)."""

    result = _features(
        "--out", str(tmp_path / "out"), store=unscoped, milestone="milestone:unscoped"
    )

    assert result.exit_code == ExitCode.FINDINGS
    assert result.stdout == ""
    assert not (tmp_path / "out").exists()
