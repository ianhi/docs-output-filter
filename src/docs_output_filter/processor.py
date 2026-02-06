"""StreamingProcessor — incremental parser for documentation build output.

Buffers lines from stdin, detects chunk boundaries (build complete, server started,
rebuild started), and triggers parsing at those boundaries. Supports both MkDocs
and Sphinx via the backend system with auto-detection.

Key class:
- StreamingProcessor: Stateful line-by-line processor with buffer management,
  issue deduplication, info message collection, and optional state file writing.

Used by all streaming-based modes (streaming, interactive, wrap).

Update this docstring if you add new processing stages, change the boundary
detection flow, or modify the buffer management strategy.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from rich.console import Console

from docs_output_filter.backends import Backend, detect_backend
from docs_output_filter.backends.mkdocs import (
    detect_chunk_boundary as mkdocs_detect_chunk_boundary,
)
from docs_output_filter.backends.mkdocs import (
    extract_build_info as mkdocs_extract_build_info,
)
from docs_output_filter.backends.mkdocs import (
    parse_info_messages as mkdocs_parse_info_messages,
)
from docs_output_filter.backends.mkdocs import (
    parse_mkdocs_output,
)
from docs_output_filter.display import print_issue
from docs_output_filter.state import (
    StateFileData,
    write_state_file,
)
from docs_output_filter.types import (
    BuildInfo,
    ChunkBoundary,
    InfoCategory,
    InfoMessage,
    Issue,
    Level,
)


class StreamingProcessor:
    """Processes build output incrementally for streaming mode.

    Supports both MkDocs and Sphinx output via the backend system.
    When tool is AUTO, auto-detects the backend from output.
    """

    BUFFER_MAX_SIZE: int = 200  # Keep last N lines for context
    RAW_BUFFER_MAX_SIZE: int = 500  # Keep last N lines for state file

    def __init__(
        self,
        console: Console,
        verbose: bool = False,
        errors_only: bool = False,
        on_issue: Callable[[Issue], None] | None = None,
        write_state: bool = False,
        backend: Backend | None = None,
    ):
        self.console = console
        self.verbose = verbose
        self.errors_only = errors_only
        self.on_issue = on_issue or (lambda issue: print_issue(console, issue, verbose))
        self.write_state = write_state
        self.backend = backend

        self.buffer: list[str] = []
        self.raw_buffer: list[str] = []  # All lines for state file
        self.all_issues: list[Issue] = []
        self.all_info_messages: list[InfoMessage] = []  # Important INFO messages
        self.seen_issues: set[tuple[Level, str]] = set()
        self.seen_info: set[tuple[InfoCategory, str, str | None]] = set()  # Dedupe info messages
        self.build_info = BuildInfo()
        self.prev_line: str | None = None
        self._pending_display = False
        self.saw_build_output = False  # Track if we saw valid build output
        self.in_serve_mode = False  # Track if serve mode is running
        self.saw_server_error = False  # Track if server crashed (OSError, etc.)
        self.error_lines: list[str] = []  # Capture error output for display
        self.build_started_at: float | None = None  # When current build started

        # Write initial "building" state if state sharing is enabled
        if self.write_state:
            self._write_building_state()

    def process_line(self, line: str) -> None:
        """Process a single line of build output."""
        line = line.rstrip()
        self.buffer.append(line)
        self.raw_buffer.append(line)

        # Auto-detect backend if not set
        if self.backend is None:
            detected = detect_backend(line)
            if detected is not None:
                self.backend = detected

        # Detect if this looks like valid build output
        if not self.saw_build_output:
            if self.backend is not None:
                self.saw_build_output = True
            elif re.match(r"^(INFO|WARNING|ERROR|DEBUG)\s+-", line) or re.match(
                r"^\d{4}-\d{2}-\d{2}.*?(INFO|WARNING|ERROR)", line
            ):
                self.saw_build_output = True

        # Detect serve mode
        if "Serving on http" in line:
            self.in_serve_mode = True

        # Detect server errors (OSError, etc.) - only specific system errors
        stripped = line.strip()
        if (
            re.match(r"^OSError:", stripped)
            or re.match(r"^IOError:", stripped)
            or re.match(r"^PermissionError:", stripped)
            or re.match(r"^ConnectionError:", stripped)
            or "Address already in use" in line
            or "Permission denied" in line
            and "OSError" in line
        ):
            self.saw_server_error = True
        if self.saw_server_error:
            self.error_lines.append(line)

        # Keep buffers from growing too large
        if len(self.buffer) > self.BUFFER_MAX_SIZE:
            self.buffer = self.buffer[-self.BUFFER_MAX_SIZE :]
        if len(self.raw_buffer) > self.RAW_BUFFER_MAX_SIZE:
            self.raw_buffer = self.raw_buffer[-self.RAW_BUFFER_MAX_SIZE :]

        # Detect chunk boundaries (use backend if available, else mkdocs default)
        if self.backend is not None:
            boundary = self.backend.detect_chunk_boundary(line, self.prev_line)
        else:
            boundary = mkdocs_detect_chunk_boundary(line, self.prev_line)
        self.prev_line = line

        # On rebuild start, clear state
        if boundary == ChunkBoundary.REBUILD_STARTED:
            self._handle_rebuild_start()
            return

        # On build complete or server started, process any pending content
        if boundary in (ChunkBoundary.BUILD_COMPLETE, ChunkBoundary.SERVER_STARTED):
            self._process_buffer()
            self._update_build_info_from_line(line)
            self._write_state_file()
            return

        # Check if we just completed an error block
        if boundary == ChunkBoundary.ERROR_BLOCK_END:
            self._process_buffer()
            return

    def _handle_rebuild_start(self) -> None:
        """Handle the start of a rebuild (file change detected)."""
        self._process_buffer()
        self.console.print()
        self.console.print()
        self.console.print("[cyan]" + "═" * 60 + "[/cyan]")
        self.console.print("[cyan bold]🔄 File change detected — rebuilding...[/cyan bold]")
        self.console.print("[cyan]" + "═" * 60 + "[/cyan]")
        self.console.print()
        preserved_server_url = self.build_info.server_url
        self.buffer.clear()
        self.raw_buffer.clear()
        self.all_issues.clear()
        self.all_info_messages.clear()
        self.seen_issues.clear()
        self.seen_info.clear()
        self.build_info = BuildInfo(server_url=preserved_server_url)
        if self.write_state:
            self._write_building_state()

    def _write_building_state(self) -> None:
        """Write 'building' status to state file so MCP knows build is in progress."""
        import time

        self.build_started_at = time.time()
        state = StateFileData(
            issues=[],
            info_messages=[],
            build_info=self.build_info,
            raw_output=[],
            build_status="building",
            build_started_at=self.build_started_at,
        )
        write_state_file(state)

    def _write_state_file(self) -> None:
        """Write current state to the state file for MCP server access."""
        if not self.write_state:
            return

        state = StateFileData(
            issues=self.all_issues,
            info_messages=self.all_info_messages,
            build_info=self.build_info,
            raw_output=self.raw_buffer,
            build_status="complete",
            build_started_at=self.build_started_at,
        )
        write_state_file(state)

    def _process_buffer(self) -> None:
        """Process accumulated buffer and display any new issues."""
        if not self.buffer:
            return

        # Update build info
        self._update_build_info(self.buffer)

        # Parse issues using backend
        if self.backend is not None:
            issues = self.backend.parse_issues(self.buffer)
        else:
            issues = parse_mkdocs_output(self.buffer)

        # Parse important INFO messages and dedupe
        if self.backend is not None:
            info_messages = self.backend.parse_info_messages(self.buffer)
        else:
            info_messages = mkdocs_parse_info_messages(self.buffer)

        for msg in info_messages:
            info_key = (msg.category, msg.file, msg.target)
            if info_key not in self.seen_info:
                self.seen_info.add(info_key)
                self.all_info_messages.append(msg)

        # Filter and dedupe
        for issue in issues:
            if self.errors_only and issue.level != Level.ERROR:
                continue

            issue_key = (issue.level, issue.message[:100])
            if issue_key in self.seen_issues:
                continue

            self.seen_issues.add(issue_key)
            self.all_issues.append(issue)
            self.on_issue(issue)

    def _update_build_info(self, lines: list[str]) -> None:
        """Update build info from lines."""
        if self.backend is not None:
            info = self.backend.extract_build_info(lines)
        else:
            info = mkdocs_extract_build_info(lines)
        if info.server_url:
            self.build_info.server_url = info.server_url
        if info.build_dir:
            self.build_info.build_dir = info.build_dir
        if info.build_time:
            self.build_info.build_time = info.build_time
        if info.reported_warning_count is not None:
            self.build_info.reported_warning_count = info.reported_warning_count

    def _update_build_info_from_line(self, line: str) -> None:
        """Update build info from a single line."""
        self._update_build_info([line])

    def finalize(self) -> tuple[list[Issue], BuildInfo]:
        """Finalize processing and return all issues and build info."""
        self._process_buffer()
        return self.all_issues, self.build_info
