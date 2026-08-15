from typer.testing import CliRunner

from absicht import __version__
from absicht.cli import app

runner = CliRunner()


def test_version_reports_the_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"absicht {__version__}"


def test_bare_invocation_prints_help_and_succeeds() -> None:
    """No subcommand is not an error: `ab` alone should be a usable way in."""
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Absicht" in result.output
