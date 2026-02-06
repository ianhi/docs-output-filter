"""Unit tests for parsing functions (MkDocs and Sphinx backends)."""

import subprocess
import sys
from pathlib import Path

from rich.console import Console

from docs_output_filter import StreamingProcessor
from docs_output_filter.backends import detect_backend
from docs_output_filter.backends.mkdocs import (
    MkDocsBackend,
    detect_chunk_boundary,
    extract_build_info,
    is_in_multiline_block,
    parse_markdown_exec_issue,
    parse_mkdocs_output,
)
from docs_output_filter.backends.sphinx import SphinxBackend
from docs_output_filter.types import (
    BuildInfo,
    ChunkBoundary,
    InfoCategory,
    InfoMessage,
    Issue,
    Level,
    dedent_code,
    group_info_messages,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestExtractBuildInfo:
    """Tests for extract_build_info function."""

    def test_extracts_server_url(self) -> None:
        lines = [
            "INFO -  Serving on http://127.0.0.1:8000/",
        ]
        info = extract_build_info(lines)
        assert info.server_url == "http://127.0.0.1:8000/"

    def test_extracts_build_time(self) -> None:
        lines = [
            "INFO -  Documentation built in 78.99 seconds",
        ]
        info = extract_build_info(lines)
        assert info.build_time == "78.99"

    def test_extracts_build_directory(self) -> None:
        lines = [
            "INFO -  Building documentation to directory: /path/to/site",
        ]
        info = extract_build_info(lines)
        assert info.build_dir == "/path/to/site"

    def test_extracts_all_info(self) -> None:
        lines = [
            "INFO -  Building documentation to directory: /path/to/site",
            "INFO -  Serving on http://127.0.0.1:8000/",
            "INFO -  Documentation built in 1.23 seconds",
        ]
        info = extract_build_info(lines)
        assert info.server_url == "http://127.0.0.1:8000/"
        assert info.build_time == "1.23"
        assert info.build_dir == "/path/to/site"

    def test_returns_empty_when_no_info(self) -> None:
        lines = ["INFO -  Some other log line"]
        info = extract_build_info(lines)
        assert info.server_url is None
        assert info.build_time is None
        assert info.build_dir is None


class TestParseMkdocsOutput:
    """Tests for parse_mkdocs_output function."""

    def test_no_warnings_or_errors(self) -> None:
        lines = [
            "INFO -  Cleaning site directory",
            "INFO -  Building documentation to directory: /path/to/site",
            "INFO -  Documentation built in 0.12 seconds",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 0

    def test_parses_simple_warning(self) -> None:
        lines = [
            "WARNING -  Some warning message",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.WARNING
        assert issues[0].source == "mkdocs"
        assert issues[0].message == "Some warning message"

    def test_parses_simple_error(self) -> None:
        lines = [
            "ERROR -  Something bad happened",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.ERROR
        assert issues[0].source == "mkdocs"
        assert issues[0].message == "Something bad happened"

    def test_parses_broken_link_warning(self) -> None:
        lines = [
            "WARNING -  Doc file 'index.md' contains a link 'missing.md', but the target is not found among documentation files.",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.WARNING
        assert issues[0].file == "index.md"
        assert "missing.md" in issues[0].message

    def test_parses_nav_reference_warning(self) -> None:
        lines = [
            "WARNING -  A reference to 'missing.md' is included in the 'nav' configuration, which is not found in the documentation files.",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.WARNING
        assert "nav" in issues[0].message.lower()
        assert issues[0].file == "missing.md"

    def test_parses_multiple_warnings(self) -> None:
        lines = [
            "INFO -  Building...",
            "WARNING -  First warning",
            "INFO -  More info",
            "WARNING -  Second warning",
            "INFO -  Done",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 2
        assert issues[0].message == "First warning"
        assert issues[1].message == "Second warning"

    def test_strips_stderr_prefix(self) -> None:
        lines = [
            "[stderr] WARNING -  Some warning",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert issues[0].message == "Some warning"

    def test_strips_timestamp_prefix(self) -> None:
        lines = [
            "2024-01-01 12:00:00,000 - mkdocs.structure - WARNING - Some warning",
        ]
        issues = parse_mkdocs_output(lines)
        assert len(issues) == 1
        assert "2024-01-01" not in issues[0].message


class TestParseMarkdownExecIssue:
    """Tests for parse_markdown_exec_issue function."""

    def test_parses_markdown_exec_error_basic(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('test error')",
            "",
            "Output is:",
            "",
            "  Traceback (most recent call last):",
            '    File "<code block: session test; n1>", line 1, in <module>',
            "      raise ValueError('test error')",
            "  ValueError: test error",
            "",
            "INFO -  next log line",
        ]
        issue, end_idx = parse_markdown_exec_issue(lines, 0, Level.WARNING)

        assert issue is not None
        assert issue.level == Level.WARNING
        assert issue.source == "markdown_exec"
        assert "ValueError: test error" in issue.message
        assert issue.code is not None
        assert "raise ValueError" in issue.code
        assert issue.output is not None
        assert "Traceback" in issue.output

    def test_extracts_session_and_line_info(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  x = 1",
            "  y = 2",
            "  raise ValueError('error')",
            "",
            "Output is:",
            "",
            "  Traceback (most recent call last):",
            '    File "<code block: session mytest; n1>", line 3, in <module>',
            "      raise ValueError('error')",
            "  ValueError: error",
            "",
            "INFO -  Done",
        ]
        issue, end_idx = parse_markdown_exec_issue(lines, 0, Level.WARNING)

        assert issue is not None
        assert issue.file is not None
        assert "session 'mytest'" in issue.file
        assert "line 3" in issue.file

    def test_extracts_file_from_verbose_mode(self) -> None:
        lines = [
            "DEBUG   -  Reading: test.md",
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('error')",
            "",
            "Output is:",
            "",
            "  Traceback (most recent call last):",
            '    File "<code block: session test; n1>", line 1, in <module>',
            "      raise ValueError('error')",
            "  ValueError: error",
            "",
            "INFO -  Done",
        ]
        issue, end_idx = parse_markdown_exec_issue(lines, 1, Level.WARNING)

        assert issue is not None
        assert issue.file is not None
        assert "test.md" in issue.file

    def test_stops_at_next_log_line(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  print('hello')",
            "",
            "Output is:",
            "",
            "  some output",
            "",
            "INFO -  Building documentation to directory: /path",
            "INFO -  More info",
        ]
        issue, end_idx = parse_markdown_exec_issue(lines, 0, Level.WARNING)

        assert issue is not None
        assert end_idx == 10  # Should stop at the INFO line


class TestDedentCode:
    """Tests for dedent_code function."""

    def test_removes_consistent_indent(self) -> None:
        code = "  line1\n  line2\n  line3"
        result = dedent_code(code)
        assert result == "line1\nline2\nline3"

    def test_preserves_relative_indent(self) -> None:
        code = "  line1\n    line2\n  line3"
        result = dedent_code(code)
        assert result == "line1\n  line2\nline3"

    def test_handles_empty_lines(self) -> None:
        code = "  line1\n\n  line3"
        result = dedent_code(code)
        assert result == "line1\n\nline3"

    def test_returns_unchanged_if_no_indent(self) -> None:
        code = "line1\nline2"
        result = dedent_code(code)
        assert result == "line1\nline2"

    def test_handles_empty_string(self) -> None:
        result = dedent_code("")
        assert result == ""


class TestIssueDataclass:
    """Tests for Issue dataclass."""

    def test_creates_minimal_issue(self) -> None:
        issue = Issue(level=Level.WARNING, source="test", message="test message")
        assert issue.level == Level.WARNING
        assert issue.source == "test"
        assert issue.message == "test message"
        assert issue.file is None
        assert issue.code is None
        assert issue.output is None
        assert issue.line_number is None
        assert issue.warning_code is None

    def test_creates_full_issue(self) -> None:
        issue = Issue(
            level=Level.ERROR,
            source="markdown_exec",
            message="Error occurred",
            file="test.md",
            line_number=42,
            code="raise Error()",
            output="Traceback...",
            warning_code="toc.not_readable",
        )
        assert issue.level == Level.ERROR
        assert issue.file == "test.md"
        assert issue.line_number == 42
        assert issue.code == "raise Error()"
        assert issue.output == "Traceback..."
        assert issue.warning_code == "toc.not_readable"


class TestBuildInfoDataclass:
    """Tests for BuildInfo dataclass."""

    def test_creates_empty_build_info(self) -> None:
        info = BuildInfo()
        assert info.server_url is None
        assert info.build_dir is None
        assert info.build_time is None

    def test_creates_full_build_info(self) -> None:
        info = BuildInfo(
            server_url="http://localhost:8000/",
            build_dir="/path/to/site",
            build_time="1.23",
        )
        assert info.server_url == "http://localhost:8000/"
        assert info.build_dir == "/path/to/site"
        assert info.build_time == "1.23"


class TestDetectChunkBoundary:
    """Tests for detect_chunk_boundary function."""

    def test_detects_build_complete(self) -> None:
        line = "INFO -  Documentation built in 78.99 seconds"
        assert detect_chunk_boundary(line) == ChunkBoundary.BUILD_COMPLETE

    def test_detects_server_started(self) -> None:
        line = "INFO -  Serving on http://127.0.0.1:8000/"
        assert detect_chunk_boundary(line) == ChunkBoundary.SERVER_STARTED

    def test_detects_rebuild_started_file_changes(self) -> None:
        line = "INFO -  Detected file changes"
        assert detect_chunk_boundary(line) == ChunkBoundary.REBUILD_STARTED

    def test_detects_rebuild_started_reloading(self) -> None:
        line = "INFO -  Reloading docs on file change"
        assert detect_chunk_boundary(line) == ChunkBoundary.REBUILD_STARTED

    def test_returns_none_for_normal_line(self) -> None:
        line = "INFO -  Building documentation..."
        assert detect_chunk_boundary(line) == ChunkBoundary.NONE

    def test_detects_error_block_end_after_blank(self) -> None:
        line = "INFO -  Building documentation"
        prev_line = ""
        assert detect_chunk_boundary(line, prev_line) == ChunkBoundary.ERROR_BLOCK_END


class TestIsInMultilineBlock:
    """Tests for is_in_multiline_block function."""

    def test_detects_unclosed_markdown_exec_block(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('test')",
        ]
        assert is_in_multiline_block(lines) is True

    def test_detects_closed_markdown_exec_block(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('test')",
            "",
            "Output is:",
            "",
            "  ValueError: test",
            "",
            "INFO -  Done building",
        ]
        assert is_in_multiline_block(lines) is False

    def test_returns_false_for_empty_buffer(self) -> None:
        assert is_in_multiline_block([]) is False

    def test_returns_false_for_normal_lines(self) -> None:
        lines = [
            "INFO -  Building...",
            "INFO -  Done",
        ]
        assert is_in_multiline_block(lines) is False


class TestStreamingProcessor:
    """Tests for StreamingProcessor class."""

    def test_processes_simple_warning(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        def capture_issue(issue: Issue) -> None:
            captured_issues.append(issue)

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=capture_issue,
        )

        lines = [
            "INFO -  Building...",
            "WARNING -  Test warning message",
            "INFO -  Documentation built in 1.00 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        all_issues, build_info = processor.finalize()

        assert len(all_issues) == 1
        assert all_issues[0].level == Level.WARNING
        assert all_issues[0].message == "Test warning message"
        assert build_info.build_time == "1.00"

    def test_deduplicates_warnings(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: captured_issues.append(i),
        )

        lines = [
            "WARNING -  Same warning",
            "WARNING -  Same warning",
            "WARNING -  Same warning",
            "INFO -  Documentation built in 1.00 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        all_issues, _ = processor.finalize()
        assert len(all_issues) == 1

    def test_filters_errors_only(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=True,
            on_issue=lambda i: captured_issues.append(i),
        )

        lines = [
            "WARNING -  A warning",
            "ERROR -  An error",
            "INFO -  Documentation built in 1.00 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        all_issues, _ = processor.finalize()
        assert len(all_issues) == 1
        assert all_issues[0].level == Level.ERROR

    def test_extracts_build_info(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
        )

        lines = [
            "INFO -  Building documentation to directory: /path/to/site",
            "INFO -  Serving on http://127.0.0.1:8000/",
            "INFO -  Documentation built in 2.50 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        _, build_info = processor.finalize()

        assert build_info.build_dir == "/path/to/site"
        assert build_info.server_url == "http://127.0.0.1:8000/"
        assert build_info.build_time == "2.50"

    def test_buffer_size_limit(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)

        processor = StreamingProcessor(console=console, verbose=False, errors_only=False)

        for i in range(300):
            processor.process_line(f"INFO -  Line {i}")

        assert len(processor.buffer) <= StreamingProcessor.BUFFER_MAX_SIZE

    def test_detects_error_after_rebuild_during_serve(self) -> None:
        """CRITICAL: Should detect new errors introduced after initial build during serve."""
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        def capture_issue(issue: Issue) -> None:
            captured_issues.append(issue)

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=capture_issue,
        )

        # Simulate initial clean build
        initial_build = [
            "INFO -  Building documentation...",
            "INFO -  Cleaning site directory",
            "INFO -  Building documentation to directory: /path/to/site",
            "INFO -  Documentation built in 1.00 seconds",
            "INFO -  Serving on http://127.0.0.1:8000/",
        ]
        for line in initial_build:
            processor.process_line(line)

        assert len(captured_issues) == 0
        assert processor.build_info.server_url == "http://127.0.0.1:8000/"

        # Simulate file change detection and rebuild with an error
        rebuild_with_error = [
            "INFO -  Detected file changes",
            "INFO -  Building documentation...",
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "",
            "Code block is:",
            "",
            "  raise ValueError('NEW ERROR AFTER SERVE')",
            "",
            "Output is:",
            "",
            "  Traceback (most recent call last):",
            '    File "<code block: session test; n1>", line 1, in <module>',
            "      raise ValueError('NEW ERROR AFTER SERVE')",
            "  ValueError: NEW ERROR AFTER SERVE",
            "",
            "INFO -  Documentation built in 0.50 seconds",
        ]
        for line in rebuild_with_error:
            processor.process_line(line)

        all_issues, build_info = processor.finalize()
        assert len(all_issues) == 1
        assert all_issues[0].level == Level.WARNING
        assert all_issues[0].source == "markdown_exec"
        assert "NEW ERROR AFTER SERVE" in all_issues[0].message
        assert all_issues[0].code is not None
        assert "raise ValueError" in all_issues[0].code

    def test_clears_state_on_rebuild(self) -> None:
        """Should clear previous issues when rebuild starts."""
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: captured_issues.append(i),
        )

        first_build = [
            "INFO -  Building...",
            "WARNING -  First build warning",
            "INFO -  Documentation built in 1.00 seconds",
            "INFO -  Serving on http://127.0.0.1:8000/",
        ]
        for line in first_build:
            processor.process_line(line)

        assert len(captured_issues) == 1
        assert "First build" in captured_issues[0].message

        rebuild = [
            "INFO -  Detected file changes",
            "INFO -  Building...",
            "WARNING -  Second build warning",
            "INFO -  Documentation built in 0.50 seconds",
        ]
        for line in rebuild:
            processor.process_line(line)

        all_issues, _ = processor.finalize()
        assert len(all_issues) == 1
        assert "Second build" in all_issues[0].message

    def test_multiple_rebuilds_each_detected(self) -> None:
        """Should detect issues across multiple rebuilds during serve."""
        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: captured_issues.append(i),
        )

        for line in [
            "INFO -  Building...",
            "INFO -  Documentation built in 1.00 seconds",
            "INFO -  Serving on http://127.0.0.1:8000/",
        ]:
            processor.process_line(line)

        assert len(captured_issues) == 0

        for line in [
            "INFO -  Detected file changes",
            "INFO -  Building...",
            "ERROR -  First rebuild error",
            "INFO -  Documentation built in 0.50 seconds",
        ]:
            processor.process_line(line)

        assert len(captured_issues) == 1
        assert "First rebuild" in captured_issues[0].message

        for line in [
            "INFO -  Detected file changes",
            "INFO -  Building...",
            "ERROR -  Second rebuild error",
            "INFO -  Documentation built in 0.30 seconds",
        ]:
            processor.process_line(line)

        assert len(captured_issues) == 2
        assert "Second rebuild" in captured_issues[1].message


class TestInfoMessages:
    """Tests for INFO message parsing and grouping."""

    def test_parses_broken_link(self) -> None:
        backend = MkDocsBackend()
        lines = [
            "INFO    -  Doc file 'docs/index.md' contains a link 'missing.md', but the target is not found among documentation files.",
        ]
        messages = backend.parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.BROKEN_LINK
        assert messages[0].file == "docs/index.md"
        assert messages[0].target == "missing.md"

    def test_parses_absolute_link_with_suggestion(self) -> None:
        backend = MkDocsBackend()
        lines = [
            "INFO    -  Doc file 'docs/index.md' contains an absolute link '/other.md', it was left as is. Did you mean 'other.md'?",
        ]
        messages = backend.parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.ABSOLUTE_LINK
        assert messages[0].suggestion == "other.md"

    def test_parses_missing_nav(self) -> None:
        backend = MkDocsBackend()
        lines = [
            'INFO    -  The following pages exist in the docs directory, but are not included in the "nav" configuration:',
            "  - orphan1.md",
            "  - orphan2.md",
        ]
        messages = backend.parse_info_messages(lines)
        assert len(messages) == 2
        assert all(m.category == InfoCategory.MISSING_NAV for m in messages)

    def test_groups_by_category(self) -> None:
        messages = [
            InfoMessage(category=InfoCategory.BROKEN_LINK, file="a.md", target="x.md"),
            InfoMessage(category=InfoCategory.NO_GIT_LOGS, file="b.md"),
            InfoMessage(category=InfoCategory.BROKEN_LINK, file="c.md", target="y.md"),
        ]
        groups = group_info_messages(messages)

        assert len(groups) == 2
        assert InfoCategory.BROKEN_LINK in groups
        assert InfoCategory.NO_GIT_LOGS in groups
        assert len(groups[InfoCategory.BROKEN_LINK]) == 2

    def test_returns_empty_dict_for_empty_input(self) -> None:
        groups = group_info_messages([])
        assert groups == {}


class TestStreamingProcessorInfoMessages:
    """Tests for StreamingProcessor tracking of INFO messages."""

    def test_collects_info_messages_during_build(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
        )

        lines = [
            "INFO    -  Building documentation...",
            "INFO    -  Doc file 'docs/index.md' contains a link 'broken.md', but the target is not found.",
            "[git-revision-date-localized-plugin] 'docs/new.md' has no git logs",
            "INFO    -  Documentation built in 1.00 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        processor.finalize()

        assert len(processor.all_info_messages) == 2
        cats = [m.category for m in processor.all_info_messages]
        assert InfoCategory.BROKEN_LINK in cats
        assert InfoCategory.NO_GIT_LOGS in cats

    def test_clears_info_messages_on_rebuild(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
        )

        for line in [
            "INFO    -  Building...",
            "INFO    -  Doc file 'docs/index.md' contains a link 'old.md', but the target is not found.",
            "INFO    -  Documentation built in 1.00 seconds",
            "INFO    -  Serving on http://127.0.0.1:8000/",
        ]:
            processor.process_line(line)

        assert len(processor.all_info_messages) == 1

        for line in [
            "INFO    -  Detected file changes",
            "INFO    -  Building...",
            "INFO    -  Doc file 'docs/page.md' contains a link 'new.md', but the target is not found.",
            "INFO    -  Documentation built in 0.50 seconds",
        ]:
            processor.process_line(line)

        processor.finalize()

        assert len(processor.all_info_messages) == 1
        assert processor.all_info_messages[0].target == "new.md"


# ===== Sphinx Backend Tests =====


class TestSphinxBackendDetect:
    """Tests for SphinxBackend auto-detection."""

    def test_detects_sphinx_version_line(self) -> None:
        backend = SphinxBackend()
        assert backend.detect("Running Sphinx v7.4.7") is True

    def test_detects_sphinx_autobuild_marker(self) -> None:
        backend = SphinxBackend()
        assert backend.detect("[sphinx-autobuild] Starting initial build") is True

    def test_detects_sphinx_warning_format(self) -> None:
        backend = SphinxBackend()
        assert backend.detect("/path/to/file.rst:15: WARNING: duplicate label") is True

    def test_detects_build_succeeded(self) -> None:
        backend = SphinxBackend()
        assert backend.detect("build succeeded, 3 warnings.") is True

    def test_does_not_detect_mkdocs_output(self) -> None:
        backend = SphinxBackend()
        assert backend.detect("INFO -  Building documentation...") is False
        assert backend.detect("WARNING -  Some mkdocs warning") is False


class TestSphinxParseIssues:
    """Tests for SphinxBackend.parse_issues."""

    def test_parses_warning_with_file_and_line(self) -> None:
        backend = SphinxBackend()
        lines = [
            "/path/docs/api.rst:15: WARNING: duplicate label api-reference",
        ]
        issues = backend.parse_issues(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.WARNING
        assert issues[0].source == "sphinx"
        assert issues[0].message == "duplicate label api-reference"
        assert issues[0].file == "/path/docs/api.rst"
        assert issues[0].line_number == 15

    def test_parses_warning_with_code(self) -> None:
        backend = SphinxBackend()
        lines = [
            "/path/docs/index.rst:10: WARNING: toctree contains reference to nonexisting document 'changelog' [toc.not_readable]",
        ]
        issues = backend.parse_issues(lines)
        assert len(issues) == 1
        assert issues[0].warning_code == "toc.not_readable"
        assert "toc.not_readable" not in issues[0].message
        assert "changelog" in issues[0].message

    def test_parses_error(self) -> None:
        backend = SphinxBackend()
        lines = [
            "/path/docs/conf.py:25: ERROR: Unknown config value",
        ]
        issues = backend.parse_issues(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.ERROR
        assert issues[0].source == "sphinx"

    def test_parses_warning_without_file(self) -> None:
        backend = SphinxBackend()
        lines = [
            "WARNING: document isn't included in any toctree",
        ]
        issues = backend.parse_issues(lines)
        assert len(issues) == 1
        assert issues[0].level == Level.WARNING
        assert issues[0].file is None
        assert issues[0].line_number is None

    def test_ignores_non_issue_lines(self) -> None:
        backend = SphinxBackend()
        lines = [
            "Running Sphinx v7.4.7",
            "loading translations [en]... done",
            "building [html]: targets for 75 source files that are out of date",
            "reading sources... [100%] workshops/thinking-like-xarray/README",
        ]
        issues = backend.parse_issues(lines)
        assert len(issues) == 0

    def test_parses_mystnb_warnings(self) -> None:
        """Should parse myst-nb style warnings (filepath: WARNING: message)."""
        backend = SphinxBackend()
        lines = [
            "/path/xarray_and_dask.ipynb: WARNING: Executing notebook failed: CellExecutionError [mystnb.exec]",
        ]
        issues = backend.parse_issues(lines)
        assert len(issues) == 1
        assert issues[0].file == "/path/xarray_and_dask.ipynb"
        assert "CellExecutionError" in issues[0].message
        assert issues[0].warning_code == "mystnb.exec"
        assert issues[0].line_number is None

    def test_parses_cell_execution_error_with_traceback(self) -> None:
        """Should capture traceback and cell code from CellExecutionError."""
        backend = SphinxBackend()
        lines = [
            "/path/notebook.md: WARNING: Executing notebook failed: CellExecutionError",
            "Traceback (most recent call last):",
            '  File "executor.py", line 58, in execute',
            "    executenb(nb)",
            '  File "nbclient.py", line 918, in _check_raise_for_error',
            "    raise CellExecutionError.from_cell_and_msg(cell, reply)",
            "nbclient.exceptions.CellExecutionError: An error occurred while executing the following cell:",
            "------------------",
            "import xarray as xr",
            "raise ValueError('test error')",
            "------------------",
            "",
            "ValueError: test error",
            "",
            " [mystnb.exec] [mystnb.exec]",
        ]
        issues = backend.parse_issues(lines)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.file == "/path/notebook.md"
        assert "ValueError: test error" in issue.message
        assert issue.code is not None
        assert "import xarray" in issue.code
        assert "raise ValueError" in issue.code
        assert issue.output is not None
        assert "Traceback" in issue.output

    def test_cell_execution_error_extracts_error_type(self) -> None:
        """Should extract the actual error type (e.g. ValueError) into the message."""
        backend = SphinxBackend()
        lines = [
            "/path/notebook.md: WARNING: Executing notebook failed: CellExecutionError [mystnb.exec]",
            "Traceback (most recent call last):",
            '  File "test.py", line 1',
            "nbclient.exceptions.CellExecutionError: An error occurred",
            "------------------",
            "raise TypeError('bad type')",
            "------------------",
            "",
            "TypeError: bad type",
        ]
        issues = backend.parse_issues(lines)
        assert len(issues) == 1
        assert "TypeError: bad type" in issues[0].message

    def test_cell_execution_error_without_traceback(self) -> None:
        """CellExecutionError without inline traceback (execution_show_tb=False)."""
        backend = SphinxBackend()
        lines = [
            "/path/notebook.ipynb: WARNING: Executing notebook failed: CellExecutionError [mystnb.exec]",
            "/path/notebook.ipynb: WARNING: Notebook exception traceback saved in: /tmp/report.err.log [mystnb.exec]",
        ]
        issues = backend.parse_issues(lines)
        assert len(issues) == 2
        assert "CellExecutionError" in issues[0].message
        assert "traceback saved" in issues[1].message


class TestSphinxChunkBoundary:
    """Tests for SphinxBackend.detect_chunk_boundary."""

    def test_detects_build_succeeded(self) -> None:
        backend = SphinxBackend()
        assert (
            backend.detect_chunk_boundary("build succeeded, 3 warnings.", None)
            == ChunkBoundary.BUILD_COMPLETE
        )

    def test_detects_build_finished(self) -> None:
        backend = SphinxBackend()
        assert (
            backend.detect_chunk_boundary("build finished with 2 errors, 1 warning.", None)
            == ChunkBoundary.BUILD_COMPLETE
        )

    def test_detects_serving(self) -> None:
        backend = SphinxBackend()
        assert (
            backend.detect_chunk_boundary(
                "[sphinx-autobuild] Serving on http://127.0.0.1:8000", None
            )
            == ChunkBoundary.SERVER_STARTED
        )

    def test_detects_autobuild_change(self) -> None:
        backend = SphinxBackend()
        assert (
            backend.detect_chunk_boundary(
                "[sphinx-autobuild] Detected change in /path/to/file.rst", None
            )
            == ChunkBoundary.REBUILD_STARTED
        )

    def test_returns_none_for_normal_line(self) -> None:
        backend = SphinxBackend()
        assert (
            backend.detect_chunk_boundary("reading sources... [100%] index", None)
            == ChunkBoundary.NONE
        )

    def test_detects_sphinx_crash_exit_code(self) -> None:
        """Sphinx crash should trigger BUILD_COMPLETE so buffer gets processed."""
        backend = SphinxBackend()
        assert (
            backend.detect_chunk_boundary("Sphinx exited with exit code: 2", None)
            == ChunkBoundary.BUILD_COMPLETE
        )


class TestSphinxExtractBuildInfo:
    """Tests for SphinxBackend.extract_build_info."""

    def test_extracts_html_pages_dir(self) -> None:
        backend = SphinxBackend()
        lines = [
            "The HTML pages are in /path/to/_build/html.",
        ]
        info = backend.extract_build_info(lines)
        assert info.build_dir == "/path/to/_build/html"

    def test_extracts_server_url(self) -> None:
        backend = SphinxBackend()
        lines = [
            "[sphinx-autobuild] Serving on http://127.0.0.1:8000",
        ]
        info = backend.extract_build_info(lines)
        assert info.server_url == "http://127.0.0.1:8000"


class TestSphinxDeprecationWarnings:
    """Tests for Sphinx deprecation warning parsing."""

    def test_parses_deprecation_warnings(self) -> None:
        backend = SphinxBackend()
        lines = [
            "/venv/lib/python3.11/site-packages/sphinx_rtd_theme/__init__.py:12: RemovedInSphinx80Warning: The deprecated 'app' argument is removed in Sphinx 8",
            "/venv/lib/python3.11/site-packages/sphinxcontrib/applehelp/__init__.py:4: DeprecationWarning: The applehelp extension is deprecated",
            "/venv/lib/python3.11/site-packages/sphinxcontrib/devhelp/__init__.py:4: DeprecationWarning: The devhelp extension is deprecated",
        ]
        messages = backend.parse_info_messages(lines)
        assert len(messages) >= 2  # At least the deprecation warnings
        assert all(m.category == InfoCategory.DEPRECATION_WARNING for m in messages)

    def test_groups_deprecation_by_package(self) -> None:
        backend = SphinxBackend()
        lines = [
            "/venv/lib/python3.11/site-packages/sphinxcontrib/applehelp/__init__.py:4: DeprecationWarning: The applehelp extension is deprecated",
            "/venv/lib/python3.11/site-packages/sphinxcontrib/devhelp/__init__.py:4: DeprecationWarning: The devhelp extension is deprecated",
        ]
        messages = backend.parse_info_messages(lines)
        # Both are from sphinxcontrib subpackages
        assert len(messages) >= 1

    def test_ignores_sphinx_warnings_in_info_messages(self) -> None:
        """Should not double-count Sphinx WARNING lines."""
        backend = SphinxBackend()
        lines = [
            "/path/docs/api.rst:15: WARNING: duplicate label api-reference [dupref]",
        ]
        messages = backend.parse_info_messages(lines)
        assert len(messages) == 0  # WARNING lines are handled by parse_issues


class TestAutoDetectBackend:
    """Tests for auto-detection of backend from output lines."""

    def test_detects_mkdocs_from_info_line(self) -> None:
        backend = detect_backend("INFO -  Building documentation...")
        assert backend is not None
        assert backend.tool.value == "mkdocs"

    def test_detects_sphinx_from_version_line(self) -> None:
        backend = detect_backend("Running Sphinx v7.4.7")
        assert backend is not None
        assert backend.tool.value == "sphinx"

    def test_detects_sphinx_from_autobuild(self) -> None:
        backend = detect_backend("[sphinx-autobuild] Starting initial build")
        assert backend is not None
        assert backend.tool.value == "sphinx"

    def test_returns_none_for_unknown(self) -> None:
        backend = detect_backend("some random text")
        assert backend is None


class TestSphinxFixtureOutput:
    """Tests that parse real-world Sphinx fixture output correctly."""

    def test_sphinx_warnings_fixture(self) -> None:
        """Parse the sphinx_warnings fixture and verify expected issues."""
        output = (FIXTURES_DIR / "sphinx_warnings" / "sample_output.txt").read_text()
        lines = output.splitlines()

        backend = SphinxBackend()
        issues = backend.parse_issues(lines)

        # Should find: 3 warnings (dupref, ref.undefined, toc.not_readable) + 1 (document not in toctree)
        warning_count = sum(1 for i in issues if i.level == Level.WARNING)
        assert warning_count >= 3

        # Check specific warning codes
        codes = [i.warning_code for i in issues if i.warning_code]
        assert "dupref" in codes
        assert "ref.undefined" in codes
        assert "toc.not_readable" in codes

    def test_sphinx_warnings_fixture_deprecations(self) -> None:
        """Parse deprecation warnings from sphinx_warnings fixture."""
        output = (FIXTURES_DIR / "sphinx_warnings" / "sample_output.txt").read_text()
        lines = output.splitlines()

        backend = SphinxBackend()
        info_messages = backend.parse_info_messages(lines)

        deprecation_msgs = [
            m for m in info_messages if m.category == InfoCategory.DEPRECATION_WARNING
        ]
        assert len(deprecation_msgs) >= 2  # RemovedInSphinx80Warning + DeprecationWarnings

    def test_sphinx_warnings_fixture_build_info(self) -> None:
        """Extract build info from sphinx_warnings fixture."""
        output = (FIXTURES_DIR / "sphinx_warnings" / "sample_output.txt").read_text()
        lines = output.splitlines()

        backend = SphinxBackend()
        info = backend.extract_build_info(lines)

        assert info.build_dir == "/Users/dev/myproject/docs/_build/html"

    def test_sphinx_errors_fixture(self) -> None:
        """Parse the sphinx_errors fixture and verify expected issues."""
        output = (FIXTURES_DIR / "sphinx_errors" / "sample_output.txt").read_text()
        lines = output.splitlines()

        backend = SphinxBackend()
        issues = backend.parse_issues(lines)

        error_count = sum(1 for i in issues if i.level == Level.ERROR)
        warning_count = sum(1 for i in issues if i.level == Level.WARNING)
        assert error_count == 2
        assert warning_count >= 1

    def test_sphinx_autobuild_fixture_boundaries(self) -> None:
        """Parse sphinx_autobuild fixture and verify chunk boundaries."""
        output = (FIXTURES_DIR / "sphinx_autobuild" / "sample_output.txt").read_text()
        lines = output.splitlines()

        backend = SphinxBackend()

        # Find all boundaries
        boundaries = []
        for line in lines:
            b = backend.detect_chunk_boundary(line, None)
            if b != ChunkBoundary.NONE:
                boundaries.append(b)

        assert ChunkBoundary.BUILD_COMPLETE in boundaries
        assert ChunkBoundary.SERVER_STARTED in boundaries
        assert ChunkBoundary.REBUILD_STARTED in boundaries

    def test_jupyter_book_fixture(self) -> None:
        """Parse real-world Jupyter Book (sphinx) output."""
        output = (FIXTURES_DIR / "sphinx_jupyter_book" / "sample_output.txt").read_text()
        lines = output.splitlines()

        # Should auto-detect as Sphinx
        detected = None
        for line in lines:
            detected = detect_backend(line)
            if detected is not None:
                break
        assert detected is not None
        assert detected.tool.value == "sphinx"

        # Parse issues
        issues = detected.parse_issues(lines)
        warning_count = sum(1 for i in issues if i.level == Level.WARNING)
        assert warning_count >= 1  # At least the mystnb.exec warnings

        # Extract build info
        info = detected.extract_build_info(lines)
        assert info.build_dir == "/Users/ian/Documents/dev/xarray-tutorial/_build/html"
        assert info.server_url == "http://127.0.0.1:8000"

    def test_jupyter_book_fixture_streaming(self) -> None:
        """Test streaming processing of Jupyter Book fixture."""
        output = (FIXTURES_DIR / "sphinx_jupyter_book" / "sample_output.txt").read_text()
        lines = output.splitlines()

        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: captured_issues.append(i),
        )

        for line in lines:
            processor.process_line(line)

        all_issues, build_info = processor.finalize()

        # Should auto-detect Sphinx backend
        assert processor.backend is not None
        assert processor.backend.tool.value == "sphinx"
        assert processor.saw_build_output is True

        # Should find the warnings
        assert len(all_issues) >= 1
        assert build_info.server_url == "http://127.0.0.1:8000"


class TestSphinxAutobuildRealOutput:
    """Tests using real sphinx-autobuild v9.1.0 output from xarray-indexes.

    This fixture captures the exact output order from sphinx-autobuild where:
    1. "build succeeded, 1 warning." fires BUILD_COMPLETE
    2. "The HTML pages are in docs/_build/html." fires BUILD_COMPLETE again
    3. "[sphinx-autobuild] Serving on http://..." fires SERVER_STARTED
    The server URL must be captured even though it arrives AFTER BUILD_COMPLETE.
    """

    def test_streaming_captures_server_url(self) -> None:
        """Server URL must be captured when it arrives after BUILD_COMPLETE."""
        output = (FIXTURES_DIR / "sphinx_autobuild_real" / "sample_output.txt").read_text()
        lines = output.splitlines()

        console = Console(force_terminal=False, no_color=True, width=80)
        captured_issues: list[Issue] = []

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: captured_issues.append(i),
        )

        for line in lines:
            processor.process_line(line)

        all_issues, build_info = processor.finalize()

        # Must auto-detect Sphinx
        assert processor.backend is not None
        assert processor.backend.tool.value == "sphinx"

        # Must find the toctree warning
        assert len(all_issues) == 1
        assert "cfinterval" in all_issues[0].message
        assert all_issues[0].warning_code == "toc.not_readable"
        assert all_issues[0].line_number == 100

        # Must capture server URL despite arriving after BUILD_COMPLETE
        assert build_info.server_url == "http://127.0.0.1:8000"

    def test_streaming_captures_build_dir(self) -> None:
        """Build directory must be captured from 'The HTML pages are in ...'."""
        output = (FIXTURES_DIR / "sphinx_autobuild_real" / "sample_output.txt").read_text()
        lines = output.splitlines()

        console = Console(force_terminal=False, no_color=True, width=80)
        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: None,
        )

        for line in lines:
            processor.process_line(line)

        _, build_info = processor.finalize()
        assert build_info.build_dir == "docs/_build/html"

    def test_streaming_captures_warning_count(self) -> None:
        """Build warning count must be captured from 'build succeeded, 1 warning.'."""
        output = (FIXTURES_DIR / "sphinx_autobuild_real" / "sample_output.txt").read_text()
        lines = output.splitlines()

        console = Console(force_terminal=False, no_color=True, width=80)
        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: None,
        )

        for line in lines:
            processor.process_line(line)

        _, build_info = processor.finalize()
        assert build_info.reported_warning_count == 1

    def test_streaming_captures_deprecation_warnings(self) -> None:
        """RemovedInSphinx10Warning deprecations should be captured as info messages."""
        output = (FIXTURES_DIR / "sphinx_autobuild_real" / "sample_output.txt").read_text()
        lines = output.splitlines()

        console = Console(force_terminal=False, no_color=True, width=80)
        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
            on_issue=lambda i: None,
        )

        for line in lines:
            processor.process_line(line)

        processor.finalize()
        deprecations = [
            m for m in processor.all_info_messages if m.category == InfoCategory.DEPRECATION_WARNING
        ]
        assert len(deprecations) >= 1

    def test_boundary_order_build_complete_before_server_started(self) -> None:
        """Verify boundary detection order: BUILD_COMPLETE fires before SERVER_STARTED."""
        output = (FIXTURES_DIR / "sphinx_autobuild_real" / "sample_output.txt").read_text()
        lines = output.splitlines()

        backend = SphinxBackend()
        boundaries = []
        for line in lines:
            b = backend.detect_chunk_boundary(line, None)
            if b != ChunkBoundary.NONE:
                boundaries.append(b)

        # "build succeeded" → BUILD_COMPLETE
        # "The HTML pages are in ..." → BUILD_COMPLETE
        # "[sphinx-autobuild] Serving on ..." → SERVER_STARTED
        assert boundaries == [
            ChunkBoundary.BUILD_COMPLETE,
            ChunkBoundary.BUILD_COMPLETE,
            ChunkBoundary.SERVER_STARTED,
        ]

    def test_cli_streaming_shows_server_url(self) -> None:
        """CLI streaming mode must print the server URL."""
        output = (FIXTURES_DIR / "sphinx_autobuild_real" / "sample_output.txt").read_text()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "docs_output_filter",
                "--no-progress",
                "--no-color",
                "--streaming",
            ],
            input=output,
            capture_output=True,
            text=True,
        )

        assert "cfinterval" in result.stdout, f"Warning missing:\n{result.stdout}"
        assert "toc.not_readable" in result.stdout, f"Warning code missing:\n{result.stdout}"
        assert "http://127.0.0.1:8000" in result.stdout, (
            f"Server URL missing from output:\n{result.stdout}"
        )
        # Server URL should appear exactly once (not duplicated)
        url_count = result.stdout.count("http://127.0.0.1:8000")
        assert url_count == 1, (
            f"Server URL appeared {url_count} times (expected 1):\n{result.stdout}"
        )
