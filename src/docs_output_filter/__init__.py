"""Filter documentation build output to show only warnings and errors with nice formatting.

Supports both MkDocs and Sphinx builds. This is the package facade — all public
symbols are re-exported here for backward compatibility, but the implementation
lives in focused submodules:

- cli.py: Argument parsing and main() entry point
- display.py: Rich-based formatting (print_issue, print_summary, etc.)
- processor.py: StreamingProcessor for incremental parsing
- modes.py: Run modes (streaming, batch, interactive, URL, wrap)
- remote.py: Remote build log fetching (ReadTheDocs, etc.)
- types.py: Shared data types (Issue, BuildInfo, Level, etc.)
- state.py: State file I/O for MCP server integration
- backends/: Backend protocol and implementations (MkDocs, Sphinx)
- mcp_server.py: MCP server for code agent integration

Usage:
    docs-output-filter -- mkdocs serve --livereload
    mkdocs build 2>&1 | docs-output-filter
    sphinx-build docs build 2>&1 | docs-output-filter -v

Update this docstring if you add new submodules or change the public API surface.
"""

from __future__ import annotations

from docs_output_filter.backends import Backend, BuildTool, detect_backend, get_backend
from docs_output_filter.backends.mkdocs import (
    detect_chunk_boundary,
    extract_build_info,
    is_in_multiline_block,
    parse_info_messages,
    parse_markdown_exec_issue,
    parse_mkdocs_output,
)
from docs_output_filter.cli import __version__, main
from docs_output_filter.display import (
    DisplayMode,
    print_info_groups,
    print_issue,
    print_summary,
)
from docs_output_filter.modes import run_wrap_mode
from docs_output_filter.processor import StreamingProcessor
from docs_output_filter.remote import fetch_remote_log
from docs_output_filter.state import (
    StateFileData,
    find_project_root,
    get_state_file_path,
    read_state_file,
    write_state_file,
)
from docs_output_filter.types import (
    BuildInfo,
    ChunkBoundary,
    InfoCategory,
    InfoMessage,
    Issue,
    Level,
    StreamingState,
    dedent_code,
    group_info_messages,
)

__all__ = [
    # Data classes
    "Level",
    "Issue",
    "BuildInfo",
    "StreamingState",
    "StateFileData",
    "ChunkBoundary",
    "DisplayMode",
    "InfoCategory",
    "InfoMessage",
    # Backend system
    "Backend",
    "BuildTool",
    "detect_backend",
    "get_backend",
    # Parsing functions (mkdocs - for backward compat)
    "detect_chunk_boundary",
    "is_in_multiline_block",
    "extract_build_info",
    "parse_mkdocs_output",
    "parse_markdown_exec_issue",
    "parse_info_messages",
    "group_info_messages",
    "dedent_code",
    # State file functions
    "find_project_root",
    "get_state_file_path",
    "read_state_file",
    "write_state_file",
    # Remote
    "fetch_remote_log",
    # Streaming
    "StreamingProcessor",
    # Display
    "print_issue",
    "print_info_groups",
    "print_summary",
    # Modes
    "run_wrap_mode",
    # CLI
    "__version__",
    "main",
]
