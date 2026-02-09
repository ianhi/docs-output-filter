"""Coverage gap tests for processor module.

Tests for uncovered lines in processor.py that weren't covered by existing tests.
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from docs_output_filter.backends import BuildTool
from docs_output_filter.backends.sphinx import SphinxBackend
from docs_output_filter.processor import StreamingProcessor
from docs_output_filter.state import read_state_file
from docs_output_filter.types import Issue, Level


class TestStreamingProcessorBackendOverride:
    """Tests for explicit backend override in StreamingProcessor."""

    def test_explicit_sphinx_backend_override(self) -> None:
        """Pass SphinxBackend() to constructor, verify it's used."""
        console = Console(file=StringIO())
        sphinx_backend = SphinxBackend()
        processor = StreamingProcessor(
            console=console,
            backend=sphinx_backend,
        )

        # Verify backend is set
        assert processor.backend is sphinx_backend
        assert processor.backend.tool == BuildTool.SPHINX

        # Process a Sphinx line and verify it's recognized
        processor.process_line("reading sources... [100%] index")
        assert processor.saw_build_output is True

        # Process a Sphinx warning
        processor.process_line("index.rst:10: WARNING: document not in toctree [toc.not_readable]")
        processor.process_line("build succeeded")

        # Should have parsed the issue
        assert len(processor.all_issues) == 1
        assert processor.all_issues[0].source == "sphinx"


class TestStreamingProcessorServerErrors:
    """Tests for server error detection in StreamingProcessor."""

    def test_oserror_detection(self) -> None:
        """Server error detection — OSError."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        processor.process_line("INFO -  Starting server...")
        processor.process_line("OSError: [Errno 98] Address already in use")
        processor.process_line("  File '/usr/lib/server.py', line 45, in bind")

        assert processor.saw_server_error is True
        assert len(processor.error_lines) > 0
        assert any("Address already in use" in line for line in processor.error_lines)

    def test_ioerror_detection(self) -> None:
        """Server error detection — IOError."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        processor.process_line("IOError: Unable to open socket")

        assert processor.saw_server_error is True
        assert "IOError: Unable to open socket" in processor.error_lines

    def test_permission_error_detection(self) -> None:
        """Server error detection — PermissionError."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        processor.process_line("PermissionError: [Errno 13] Permission denied")

        assert processor.saw_server_error is True

    def test_permission_denied_without_oserror(self) -> None:
        """Server error detection — 'Permission denied' without 'OSError' substring."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        processor.process_line("ERROR: Permission denied: /var/log/build.log")

        assert processor.saw_server_error is True

    def test_standalone_oserror(self) -> None:
        """Server error detection — 'OSError' in line without 'Permission denied'."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        processor.process_line("Unexpected OSError during build")

        assert processor.saw_server_error is True

    def test_connection_error_detection(self) -> None:
        """Server error detection — ConnectionError."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        processor.process_line("ConnectionError: Failed to connect to server")

        assert processor.saw_server_error is True

    def test_address_already_in_use_detection(self) -> None:
        """Server error detection — 'Address already in use' string."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        processor.process_line("ERROR: Address already in use: 127.0.0.1:8000")

        assert processor.saw_server_error is True

    def test_error_lines_captured_after_server_error(self) -> None:
        """Error lines are captured after server error detected."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        processor.process_line("OSError: Address already in use")
        processor.process_line("Traceback (most recent call last):")
        processor.process_line('  File "server.py", line 10, in start')
        processor.process_line("    server.bind((host, port))")

        # All lines after OSError should be captured
        assert len(processor.error_lines) == 4


class TestStreamingProcessorBufferManagement:
    """Tests for buffer management in StreamingProcessor."""

    def test_raw_buffer_exceeds_max_size(self) -> None:
        """Raw buffer management — exceeds RAW_BUFFER_MAX_SIZE → trimmed."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # RAW_BUFFER_MAX_SIZE is 500
        # Add 600 lines to exceed the limit
        for i in range(600):
            processor.process_line(f"Line {i}")

        # Should be trimmed to 500
        assert len(processor.raw_buffer) == 500
        # Should keep the last 500 lines
        assert processor.raw_buffer[0] == "Line 100"
        assert processor.raw_buffer[-1] == "Line 599"

    def test_buffer_exceeds_max_size(self) -> None:
        """Buffer management — exceeds BUFFER_MAX_SIZE → trimmed."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # BUFFER_MAX_SIZE is 200
        # Add 300 lines to exceed the limit
        for i in range(300):
            processor.process_line(f"INFO -  Line {i}")

        # Should be trimmed to 200
        assert len(processor.buffer) == 200
        # Should keep the last 200 lines
        assert processor.buffer[0] == "INFO -  Line 100"
        assert processor.buffer[-1] == "INFO -  Line 299"


class TestStreamingProcessorBoundaries:
    """Tests for boundary detection and processing."""

    def test_error_block_end_triggers_process_buffer(self) -> None:
        """ERROR_BLOCK_END boundary triggers _process_buffer."""
        console = Console(file=StringIO())
        issues_collected: list[Issue] = []

        def collect_issue(issue: Issue) -> None:
            issues_collected.append(issue)

        processor = StreamingProcessor(
            console=console,
            on_issue=collect_issue,
        )

        # Add a warning followed by blank line then next INFO (triggers ERROR_BLOCK_END)
        processor.process_line("WARNING -  Something is wrong")
        processor.process_line("")
        processor.process_line("INFO -  Next log message")  # Triggers ERROR_BLOCK_END

        # Should have processed the buffer and captured the warning
        assert len(issues_collected) == 1
        assert issues_collected[0].message == "Something is wrong"

    def test_process_buffer_with_empty_buffer(self) -> None:
        """_process_buffer with empty buffer → noop."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Clear buffer and call _process_buffer
        processor.buffer.clear()
        processor._process_buffer()

        # Should not crash and should have no issues
        assert len(processor.all_issues) == 0


class TestStreamingProcessorBuildInfo:
    """Tests for build info extraction."""

    def test_update_build_info_from_line_delegates(self) -> None:
        """_update_build_info_from_line delegates to _update_build_info."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Process a line with server URL
        line = "INFO -  Serving on http://127.0.0.1:8000/"
        processor._update_build_info_from_line(line)

        # Should have extracted the URL
        assert processor.build_info.server_url == "http://127.0.0.1:8000/"


class TestStreamingProcessorFinalize:
    """Tests for finalize method."""

    def test_finalize_processes_remaining_buffer(self) -> None:
        """finalize processes remaining buffer."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Add lines to buffer without triggering a boundary
        processor.process_line("INFO -  Building...")
        processor.process_line("WARNING -  Final warning")

        # Finalize should process the buffer
        issues, build_info = processor.finalize()

        # Should have captured the warning
        assert len(issues) == 1
        assert issues[0].message == "Final warning"


class TestStreamingProcessorStateWriting:
    """Tests for state file writing."""

    def test_write_state_on_init(self) -> None:
        """write_state=True → writes building state on init."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(
            console=console,
            write_state=True,
        )

        # Should have written initial "building" state
        assert processor.build_started_at is not None

        # Read state file and verify
        state = read_state_file()
        assert state is not None
        assert state.build_status == "building"
        assert state.build_started_at is not None

    def test_write_state_on_build_complete(self) -> None:
        """write_state=True → writes state on build complete."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(
            console=console,
            write_state=True,
        )

        # Process some build output
        processor.process_line("INFO -  Building documentation")
        processor.process_line("WARNING -  Test warning")
        processor.process_line("INFO -  Documentation built in 1.5 seconds")  # BUILD_COMPLETE

        # Should have written complete state
        state = read_state_file()
        assert state is not None
        assert state.build_status == "complete"
        assert len(state.issues) == 1
        assert state.issues[0].message == "Test warning"
        assert state.build_info.build_time == "1.5"


class TestStreamingProcessorRebuildStart:
    """Tests for rebuild start handling."""

    def test_handle_rebuild_start_preserves_server_url(self) -> None:
        """_handle_rebuild_start preserves server_url."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Set initial state
        processor.build_info.server_url = "http://127.0.0.1:8000/"
        processor.all_issues.append(
            Issue(level=Level.WARNING, source="mkdocs", message="Old warning")
        )

        # Trigger rebuild
        processor._handle_rebuild_start()

        # Server URL should be preserved
        assert processor.build_info.server_url == "http://127.0.0.1:8000/"

        # Issues should be cleared
        assert len(processor.all_issues) == 0

    def test_handle_rebuild_start_clears_buffers(self) -> None:
        """_handle_rebuild_start clears buffers and state."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Set initial state
        processor.buffer = ["line1", "line2", "line3"]
        processor.raw_buffer = ["raw1", "raw2"]
        processor.all_issues.append(
            Issue(level=Level.WARNING, source="mkdocs", message="Old warning")
        )
        processor.all_info_messages = [
            # Add some dummy info message
        ]
        processor.seen_issues.add((Level.WARNING, "something"))

        # Trigger rebuild
        processor._handle_rebuild_start()

        # Everything should be cleared
        assert len(processor.buffer) == 0
        assert len(processor.raw_buffer) == 0
        assert len(processor.all_issues) == 0
        assert len(processor.all_info_messages) == 0
        assert len(processor.seen_issues) == 0

    def test_handle_rebuild_start_writes_building_state(self) -> None:
        """_handle_rebuild_start writes building state when write_state=True."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(
            console=console,
            write_state=True,
        )

        # Initial state
        processor.process_line("INFO -  Building...")
        processor.process_line("INFO -  Documentation built in 1.0 seconds")

        # Read state (should be complete)
        state = read_state_file()
        assert state is not None
        assert state.build_status == "complete"

        # Trigger rebuild
        processor._handle_rebuild_start()

        # State should be back to building
        state = read_state_file()
        assert state is not None
        assert state.build_status == "building"


class TestStreamingProcessorAutoDetection:
    """Tests for backend auto-detection."""

    def test_auto_detect_backend_from_mkdocs_line(self) -> None:
        """Auto-detect backend from MkDocs line."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Initially no backend
        assert processor.backend is None

        # Process MkDocs line
        processor.process_line("INFO -  Building documentation")

        # Should have auto-detected MkDocs
        assert processor.backend is not None
        assert processor.backend.tool == BuildTool.MKDOCS

    def test_auto_detect_backend_from_sphinx_line(self) -> None:
        """Auto-detect backend from Sphinx line."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Initially no backend
        assert processor.backend is None

        # Process Sphinx line
        processor.process_line("reading sources... [100%] index")

        # Should have auto-detected Sphinx
        assert processor.backend is not None
        assert processor.backend.tool == BuildTool.SPHINX

    def test_saw_build_output_detection_without_backend(self) -> None:
        """Detect saw_build_output from MkDocs patterns even without backend."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Process a line that matches MkDocs pattern but doesn't auto-detect
        processor.process_line("INFO -  Some message")

        # Should mark as saw_build_output
        assert processor.saw_build_output is True

    def test_saw_build_output_with_timestamp_format(self) -> None:
        """Detect saw_build_output from timestamped format."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        processor.process_line("2024-02-06 10:30:45,123 - INFO - Building")

        # Should mark as saw_build_output
        assert processor.saw_build_output is True

    def test_saw_build_output_fallback_unreachable(self) -> None:
        """Line 116 in processor.py is unreachable: any line matching the regex also
        triggers detect_backend, so backend is set before the elif is evaluated.
        A pragma: no cover was added to line 116 instead of testing it."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)
        # Verify that processing a matching line sets backend (not the elif fallback)
        processor.process_line("INFO -  Building documentation")
        assert processor.backend is not None
        assert processor.saw_build_output is True


class TestStreamingProcessorServeMode:
    """Tests for serve mode detection."""

    def test_detect_serve_mode(self) -> None:
        """Detect serve mode from 'Serving on http' line."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        assert processor.in_serve_mode is False

        processor.process_line("INFO -  Serving on http://127.0.0.1:8000/")

        assert processor.in_serve_mode is True


class TestStreamingProcessorDeduplication:
    """Tests for issue and info message deduplication."""

    def test_issue_deduplication(self) -> None:
        """Issues are deduplicated by (level, message[:100])."""
        console = Console(file=StringIO())
        issues_collected: list[Issue] = []

        def collect_issue(issue: Issue) -> None:
            issues_collected.append(issue)

        processor = StreamingProcessor(
            console=console,
            on_issue=collect_issue,
        )

        # Process same warning twice
        processor.process_line("WARNING -  Duplicate warning")
        processor.process_line("INFO -  Documentation built in 1.0 seconds")
        processor.process_line("WARNING -  Duplicate warning")
        processor.process_line("INFO -  Documentation built in 1.1 seconds")

        # Should only see the warning once
        assert len(issues_collected) == 1

    def test_info_message_deduplication(self) -> None:
        """Info messages are deduplicated by (category, file, target)."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Process same broken link warning twice
        processor.process_line(
            "INFO -  Doc file 'index.md' contains a link 'missing.md', but the target is not found"
        )
        processor.process_line("INFO -  Documentation built in 1.0 seconds")
        processor.process_line(
            "INFO -  Doc file 'index.md' contains a link 'missing.md', but the target is not found"
        )
        processor.process_line("INFO -  Documentation built in 1.1 seconds")

        # Should only have one info message
        assert len(processor.all_info_messages) == 1


class TestStreamingProcessorErrorsOnly:
    """Tests for errors_only filter."""

    def test_errors_only_filters_warnings(self) -> None:
        """errors_only=True filters out warnings."""
        console = Console(file=StringIO())
        issues_collected: list[Issue] = []

        def collect_issue(issue: Issue) -> None:
            issues_collected.append(issue)

        processor = StreamingProcessor(
            console=console,
            errors_only=True,
            on_issue=collect_issue,
        )

        processor.process_line("WARNING -  This should be filtered")
        processor.process_line("ERROR -  This should appear")
        processor.process_line("INFO -  Documentation built in 1.0 seconds")

        # Should only have the error
        assert len(issues_collected) == 1
        assert issues_collected[0].level == Level.ERROR
        assert issues_collected[0].message == "This should appear"


class TestStreamingProcessorIntegration:
    """Integration tests with realistic build scenarios."""

    def test_full_mkdocs_build_cycle(self) -> None:
        """Full MkDocs build cycle with warnings and build complete."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console, write_state=True)

        # Simulate a full build
        processor.process_line("INFO -  Cleaning site directory")
        processor.process_line("INFO -  Building documentation to directory: /tmp/site")
        processor.process_line("WARNING -  Doc file 'index.md' contains a broken link")
        processor.process_line("WARNING -  Navigation reference to 'missing.md' not found")
        processor.process_line("INFO -  Documentation built in 2.5 seconds")
        processor.process_line("INFO -  Serving on http://127.0.0.1:8000/")

        # Verify results
        assert len(processor.all_issues) == 2
        assert processor.build_info.build_time == "2.5"
        assert processor.build_info.build_dir == "/tmp/site"
        assert processor.build_info.server_url == "http://127.0.0.1:8000/"

        # Verify state file
        state = read_state_file()
        assert state is not None
        assert len(state.issues) == 2
        assert state.build_status == "complete"

    def test_full_sphinx_build_cycle(self) -> None:
        """Full Sphinx build cycle with auto-detection."""
        console = Console(file=StringIO())
        processor = StreamingProcessor(console=console)

        # Simulate Sphinx build
        processor.process_line("Running Sphinx v7.2.6")
        processor.process_line("reading sources... [100%] index")
        processor.process_line("writing output... [100%] index")
        processor.process_line("index.rst:10: WARNING: document not in toctree [toc.not_readable]")
        processor.process_line("build succeeded, 1 warning.")
        processor.process_line("The HTML pages are in _build/html.")

        # Verify backend was detected
        assert processor.backend is not None
        assert processor.backend.tool == BuildTool.SPHINX

        # Verify issue parsed
        assert len(processor.all_issues) == 1
        assert processor.all_issues[0].warning_code == "toc.not_readable"
        assert processor.build_info.reported_warning_count == 1
