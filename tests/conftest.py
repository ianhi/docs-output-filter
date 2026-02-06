"""Pytest configuration and fixtures for docs-output-filter tests."""

import subprocess
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def basic_site_dir(fixtures_dir: Path) -> Path:
    """Return the path to the basic_site fixture."""
    return fixtures_dir / "basic_site"


@pytest.fixture
def markdown_exec_error_dir(fixtures_dir: Path) -> Path:
    """Return the path to the markdown_exec_error fixture."""
    return fixtures_dir / "markdown_exec_error"


@pytest.fixture
def broken_links_dir(fixtures_dir: Path) -> Path:
    """Return the path to the broken_links fixture."""
    return fixtures_dir / "broken_links"


@pytest.fixture
def multiple_errors_dir(fixtures_dir: Path) -> Path:
    """Return the path to the multiple_errors fixture."""
    return fixtures_dir / "multiple_errors"


@pytest.fixture
def sphinx_warnings_output(fixtures_dir: Path) -> str:
    """Return sample Sphinx output with warnings."""
    return (fixtures_dir / "sphinx_warnings" / "sample_output.txt").read_text()


@pytest.fixture
def sphinx_errors_output(fixtures_dir: Path) -> str:
    """Return sample Sphinx output with errors."""
    return (fixtures_dir / "sphinx_errors" / "sample_output.txt").read_text()


@pytest.fixture
def sphinx_autobuild_output(fixtures_dir: Path) -> str:
    """Return sample sphinx-autobuild output."""
    return (fixtures_dir / "sphinx_autobuild" / "sample_output.txt").read_text()


def run_mkdocs_build(site_dir: Path, verbose: bool = False) -> str:
    """Run mkdocs build in the given directory and return stdout+stderr."""
    cmd = ["mkdocs", "build", "--clean"]
    if verbose:
        cmd.append("--verbose")
    result = subprocess.run(
        cmd,
        cwd=site_dir,
        capture_output=True,
        text=True,
    )
    # Combine stdout and stderr (mkdocs outputs to both)
    return result.stdout + result.stderr


def run_filter(input_text: str, *args: str) -> tuple[str, int]:
    """Run docs-output-filter with the given input and return (output, exit_code)."""
    cmd = ["python", "-m", "docs_output_filter", "--no-progress", "--no-color", *args]
    result = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr, result.returncode


run_mkdocs_filter = run_filter  # alias used in test_integration.py


@pytest.fixture
def run_build():
    """Fixture that provides a function to run mkdocs build."""
    return run_mkdocs_build


@pytest.fixture
def run_filter_fixture():
    """Fixture that provides a function to run docs-output-filter."""
    return run_filter
