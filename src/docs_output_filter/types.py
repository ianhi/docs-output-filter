"""Shared types for docs-output-filter.

This module contains all data types used across the CLI, backends, and MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Level(Enum):
    """Log level for issues."""

    ERROR = "ERROR"
    WARNING = "WARNING"


class InfoCategory(Enum):
    """Categories for important INFO messages that should be shown."""

    BROKEN_LINK = "broken_link"  # Link target not found
    ABSOLUTE_LINK = "absolute_link"  # Absolute link left as-is
    UNRECOGNIZED_LINK = "unrecognized_link"  # Unrecognized relative link
    MISSING_NAV = "missing_nav"  # Page not in nav
    NO_GIT_LOGS = "no_git_logs"  # Git revision plugin can't find logs
    DEPRECATION_WARNING = "deprecation_warning"  # Python/Sphinx deprecation warnings


@dataclass
class InfoMessage:
    """An important INFO message that should be shown (grouped with similar messages)."""

    category: InfoCategory
    file: str  # The doc file this relates to
    target: str | None = None  # Link target, suggested fix, etc.
    suggestion: str | None = None  # e.g., "Did you mean 'index.md'?"


@dataclass
class Issue:
    """A warning or error from build output."""

    level: Level
    source: str
    message: str
    file: str | None = None
    line_number: int | None = None  # Explicit line number (Sphinx provides this)
    code: str | None = None
    output: str | None = None
    warning_code: str | None = None  # Sphinx warning code e.g. "toc.not_readable"


@dataclass
class BuildInfo:
    """Information extracted from the build output."""

    server_url: str | None = None
    build_dir: str | None = None
    build_time: str | None = None
    reported_warning_count: int | None = None  # Warning count reported by build tool


@dataclass
class StreamingState:
    """State for streaming processor."""

    buffer: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    build_info: BuildInfo = field(default_factory=BuildInfo)
    seen_issues: set[tuple[Level, str]] = field(default_factory=set)
    in_markdown_exec_block: bool = False


class ChunkBoundary(Enum):
    """Types of chunk boundaries in build output."""

    BUILD_COMPLETE = "build_complete"  # "Documentation built in X seconds" or "build succeeded"
    SERVER_STARTED = "server_started"  # "Serving on http://..."
    REBUILD_STARTED = "rebuild_started"  # "Detected file changes" or sphinx-autobuild rebuild
    ERROR_BLOCK_END = "error_block_end"  # End of multi-line error block
    NONE = "none"


def group_info_messages(
    messages: list[InfoMessage],
) -> dict[InfoCategory, list[InfoMessage]]:
    """Group InfoMessages by category."""
    groups: dict[InfoCategory, list[InfoMessage]] = {}
    for msg in messages:
        if msg.category not in groups:
            groups[msg.category] = []
        groups[msg.category].append(msg)
    return groups


def dedent_code(code: str) -> str:
    """Remove consistent leading whitespace from code."""
    lines = code.split("\n")
    if not lines:
        return code

    min_indent = float("inf")
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            min_indent = min(min_indent, indent)

    if min_indent < float("inf"):
        return "\n".join(
            line[int(min_indent) :] if len(line) > min_indent else line for line in lines
        )
    return code
