"""Backend system for docs-output-filter.

Each documentation tool (mkdocs, Sphinx) has a backend that implements
the parsing interface. The Backend protocol defines what each backend must provide.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from docs_output_filter.types import (
    BuildInfo,
    ChunkBoundary,
    InfoMessage,
    Issue,
)


class BuildTool(Enum):
    """Supported documentation build tools."""

    MKDOCS = "mkdocs"
    SPHINX = "sphinx"
    AUTO = "auto"


@runtime_checkable
class Backend(Protocol):
    """Interface each build tool backend must implement."""

    tool: BuildTool

    def detect(self, line: str) -> bool:
        """Return True if this line indicates this backend's tool."""
        ...  # pragma: no cover

    def parse_issues(self, lines: list[str]) -> list[Issue]:
        """Parse warnings/errors from build output lines."""
        ...  # pragma: no cover

    def parse_info_messages(self, lines: list[str]) -> list[InfoMessage]:
        """Parse INFO-level messages (broken links, deprecations, etc.)."""
        ...  # pragma: no cover

    def detect_chunk_boundary(self, line: str, prev_line: str | None) -> ChunkBoundary:
        """Detect streaming chunk boundaries."""
        ...  # pragma: no cover

    def extract_build_info(self, lines: list[str]) -> BuildInfo:
        """Extract server URL, build dir, build time."""
        ...  # pragma: no cover

    def is_in_multiline_block(self, lines: list[str]) -> bool:
        """Check if buffer is in an unclosed multi-line block."""
        ...  # pragma: no cover


# Registry of available backends (lazily populated)
_backends: list[Backend] | None = None


def _get_all_backends() -> list[Backend]:
    """Get instances of all available backends."""
    global _backends
    if _backends is None:
        from docs_output_filter.backends.mkdocs import MkDocsBackend
        from docs_output_filter.backends.sphinx import SphinxBackend

        _backends = [MkDocsBackend(), SphinxBackend()]
    return _backends


def detect_backend(line: str) -> Backend | None:
    """Auto-detect backend from a single line of output.

    Returns the first backend whose detect() method returns True, or None.
    """
    for backend in _get_all_backends():
        if backend.detect(line):
            return backend
    return None


def detect_backend_from_lines(
    lines: list[str], fallback_tool: BuildTool = BuildTool.MKDOCS
) -> Backend:
    """Auto-detect backend by scanning lines, falling back to the given tool."""
    for line in lines:
        backend = detect_backend(line)
        if backend is not None:
            return backend
    return get_backend(fallback_tool)


def get_backend(tool: BuildTool) -> Backend:
    """Get backend by explicit tool choice.

    For BuildTool.AUTO, returns the MkDocs backend as default
    (auto-detection should be used during streaming instead).
    """
    from docs_output_filter.backends.mkdocs import MkDocsBackend
    from docs_output_filter.backends.sphinx import SphinxBackend

    if tool == BuildTool.SPHINX:
        return SphinxBackend()
    # Default to MkDocs for both MKDOCS and AUTO
    return MkDocsBackend()
