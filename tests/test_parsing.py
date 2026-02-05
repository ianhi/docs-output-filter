"""Unit tests for mkdocs output parsing functions."""

from rich.console import Console

from mkdocs_filter import (
    BuildInfo,
    ChunkBoundary,
    Issue,
    Level,
    StreamingProcessor,
    dedent_code,
    detect_chunk_boundary,
    extract_build_info,
    is_in_multiline_block,
    parse_markdown_exec_issue,
    parse_mkdocs_output,
)
from mkdocs_filter.parsing import (
    InfoCategory,
    InfoMessage,
    group_info_messages,
    parse_info_messages,
)


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
        # The timestamp should be stripped
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

    def test_creates_full_issue(self) -> None:
        issue = Issue(
            level=Level.ERROR,
            source="markdown_exec",
            message="Error occurred",
            file="test.md",
            code="raise Error()",
            output="Traceback...",
        )
        assert issue.level == Level.ERROR
        assert issue.file == "test.md"
        assert issue.code == "raise Error()"
        assert issue.output == "Traceback..."


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

        # Add more lines than buffer max size
        for i in range(300):
            processor.process_line(f"INFO -  Line {i}")

        # Buffer should be trimmed to max size
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

        # At this point, no issues should be detected
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

        # Should have detected the new error
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

        # First build with a warning
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

        # Rebuild after file change - this should clear state
        rebuild = [
            "INFO -  Detected file changes",
            "INFO -  Building...",
            "WARNING -  Second build warning",
            "INFO -  Documentation built in 0.50 seconds",
        ]
        for line in rebuild:
            processor.process_line(line)

        # After finalize, should only have the second warning (state was cleared)
        all_issues, _ = processor.finalize()
        # captured_issues will have both (callback was called for both)
        # but processor.all_issues should only have the second one
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

        # Initial clean build
        for line in [
            "INFO -  Building...",
            "INFO -  Documentation built in 1.00 seconds",
            "INFO -  Serving on http://127.0.0.1:8000/",
        ]:
            processor.process_line(line)

        assert len(captured_issues) == 0

        # First rebuild with error
        for line in [
            "INFO -  Detected file changes",
            "INFO -  Building...",
            "ERROR -  First rebuild error",
            "INFO -  Documentation built in 0.50 seconds",
        ]:
            processor.process_line(line)

        # Should have captured one error
        assert len(captured_issues) == 1
        assert "First rebuild" in captured_issues[0].message

        # Second rebuild with different error
        for line in [
            "INFO -  Detected file changes",
            "INFO -  Building...",
            "ERROR -  Second rebuild error",
            "INFO -  Documentation built in 0.30 seconds",
        ]:
            processor.process_line(line)

        # Should have captured two errors total (one from each rebuild)
        assert len(captured_issues) == 2
        assert "Second rebuild" in captured_issues[1].message


class TestInfoMessageDataclass:
    """Tests for InfoMessage dataclass."""

    def test_creates_minimal_info_message(self) -> None:
        msg = InfoMessage(category=InfoCategory.BROKEN_LINK, file="docs/index.md")
        assert msg.category == InfoCategory.BROKEN_LINK
        assert msg.file == "docs/index.md"
        assert msg.target is None
        assert msg.suggestion is None

    def test_creates_full_info_message(self) -> None:
        msg = InfoMessage(
            category=InfoCategory.ABSOLUTE_LINK,
            file="docs/index.md",
            target="/other.md",
            suggestion="other.md",
        )
        assert msg.category == InfoCategory.ABSOLUTE_LINK
        assert msg.file == "docs/index.md"
        assert msg.target == "/other.md"
        assert msg.suggestion == "other.md"


class TestInfoCategoryEnum:
    """Tests for InfoCategory enum values."""

    def test_broken_link_category(self) -> None:
        assert InfoCategory.BROKEN_LINK.value == "broken_link"

    def test_absolute_link_category(self) -> None:
        assert InfoCategory.ABSOLUTE_LINK.value == "absolute_link"

    def test_unrecognized_link_category(self) -> None:
        assert InfoCategory.UNRECOGNIZED_LINK.value == "unrecognized_link"

    def test_missing_nav_category(self) -> None:
        assert InfoCategory.MISSING_NAV.value == "missing_nav"

    def test_no_git_logs_category(self) -> None:
        assert InfoCategory.NO_GIT_LOGS.value == "no_git_logs"


class TestParseInfoMessages:
    """Tests for parse_info_messages function."""

    def test_parses_broken_link_single_quotes(self) -> None:
        lines = [
            "INFO    -  Doc file 'docs/index.md' contains a link 'missing.md', but the target is not found among documentation files.",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.BROKEN_LINK
        assert messages[0].file == "docs/index.md"
        assert messages[0].target == "missing.md"

    def test_parses_broken_link_double_quotes(self) -> None:
        lines = [
            'INFO    -  Doc file "docs/page.md" contains a link "other.md", but the target is not found.',
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.BROKEN_LINK
        assert messages[0].file == "docs/page.md"
        assert messages[0].target == "other.md"

    def test_parses_absolute_link(self) -> None:
        lines = [
            "INFO    -  Doc file 'docs/index.md' contains an absolute link '/api/index.md', it was left as is.",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.ABSOLUTE_LINK
        assert messages[0].file == "docs/index.md"
        assert messages[0].target == "/api/index.md"
        assert messages[0].suggestion is None

    def test_parses_absolute_link_with_suggestion(self) -> None:
        lines = [
            "INFO    -  Doc file 'docs/index.md' contains an absolute link '/other.md', it was left as is. Did you mean 'other.md'?",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.ABSOLUTE_LINK
        assert messages[0].file == "docs/index.md"
        assert messages[0].target == "/other.md"
        assert messages[0].suggestion == "other.md"

    def test_parses_unrecognized_relative_link(self) -> None:
        lines = [
            "INFO    -  Doc file 'docs/guide.md' contains an unrecognized relative link 'broken-link.md', it was left as is.",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.UNRECOGNIZED_LINK
        assert messages[0].file == "docs/guide.md"
        assert messages[0].target == "broken-link.md"

    def test_parses_unrecognized_link_with_suggestion(self) -> None:
        lines = [
            "INFO    -  Doc file 'docs/guide.md' contains an unrecognized relative link 'typo.md', it was left as is. Did you mean 'page.md'?",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.UNRECOGNIZED_LINK
        assert messages[0].suggestion == "page.md"

    def test_parses_no_git_logs(self) -> None:
        lines = [
            "[git-revision-date-localized-plugin] 'docs/new-page.md' has no git logs, cannot get revision date. Is git installed?",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.NO_GIT_LOGS
        assert messages[0].file == "docs/new-page.md"

    def test_parses_no_git_logs_double_quotes(self) -> None:
        lines = [
            '[git-revision-date-localized-plugin] "docs/draft.md" has no git logs',
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.NO_GIT_LOGS
        assert messages[0].file == "docs/draft.md"

    def test_parses_missing_nav_single_file(self) -> None:
        lines = [
            'INFO    -  The following pages exist in the docs directory, but are not included in the "nav" configuration:',
            "  - orphan.md",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.MISSING_NAV
        assert messages[0].file == "orphan.md"

    def test_parses_missing_nav_multiple_files(self) -> None:
        lines = [
            'INFO    -  The following pages exist in the docs directory, but are not included in the "nav" configuration:',
            "  - orphan1.md",
            "  - orphan2.md",
            "  - subdir/orphan3.md",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 3
        assert all(m.category == InfoCategory.MISSING_NAV for m in messages)
        assert messages[0].file == "orphan1.md"
        assert messages[1].file == "orphan2.md"
        assert messages[2].file == "subdir/orphan3.md"

    def test_missing_nav_block_ends_at_non_dash_line(self) -> None:
        lines = [
            'INFO    -  The following pages exist in the docs directory, but are not included in the "nav" configuration:',
            "  - orphan.md",
            "INFO    -  Building documentation...",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].file == "orphan.md"

    def test_parses_multiple_different_info_types(self) -> None:
        lines = [
            "INFO    -  Building documentation...",
            "INFO    -  Doc file 'docs/index.md' contains a link 'broken.md', but the target is not found.",
            "[git-revision-date-localized-plugin] 'docs/new.md' has no git logs",
            "INFO    -  Doc file 'docs/page.md' contains an absolute link '/other.md', it was left as is.",
            "INFO    -  Documentation built in 1.00 seconds",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 3
        categories = [m.category for m in messages]
        assert InfoCategory.BROKEN_LINK in categories
        assert InfoCategory.NO_GIT_LOGS in categories
        assert InfoCategory.ABSOLUTE_LINK in categories

    def test_ignores_warning_lines(self) -> None:
        lines = [
            "WARNING -  markdown_exec: Execution of python code block exited with errors",
            "INFO    -  Doc file 'docs/index.md' contains a link 'broken.md', but the target is not found.",
        ]
        messages = parse_info_messages(lines)
        # Should only get the INFO message, not the WARNING
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.BROKEN_LINK

    def test_ignores_error_lines(self) -> None:
        lines = [
            "ERROR   -  Configuration error: 'nav' contains invalid entry",
            "INFO    -  Doc file 'docs/index.md' contains a link 'broken.md', but the target is not found.",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 1
        assert messages[0].category == InfoCategory.BROKEN_LINK

    def test_returns_empty_for_no_matches(self) -> None:
        lines = [
            "INFO    -  Building documentation...",
            "INFO    -  Cleaning site directory",
            "INFO    -  Documentation built in 0.50 seconds",
        ]
        messages = parse_info_messages(lines)
        assert len(messages) == 0

    def test_returns_empty_for_empty_input(self) -> None:
        messages = parse_info_messages([])
        assert len(messages) == 0

    def test_handles_mixed_real_output(self) -> None:
        """Test with realistic mkdocs output mixing INFO messages."""
        lines = [
            "INFO    -  Building documentation...",
            "INFO    -  Cleaning site directory",
            'INFO    -  The following pages exist in the docs directory, but are not included in the "nav" configuration:',
            "  - draft.md",
            "  - notes/scratch.md",
            "[git-revision-date-localized-plugin] 'docs/draft.md' has no git logs, cannot get revision date.",
            "INFO    -  Doc file 'docs/index.md' contains a link 'missing.md', but the target is not found among documentation files.",
            "INFO    -  Doc file 'docs/api.md' contains an absolute link '/users/list', it was left as is.",
            "INFO    -  Documentation built in 2.34 seconds",
        ]
        messages = parse_info_messages(lines)

        # Should find: 2 missing nav, 1 no git logs, 1 broken link, 1 absolute link
        assert len(messages) == 5

        # Check we got the right categories
        cats = [m.category for m in messages]
        assert cats.count(InfoCategory.MISSING_NAV) == 2
        assert cats.count(InfoCategory.NO_GIT_LOGS) == 1
        assert cats.count(InfoCategory.BROKEN_LINK) == 1
        assert cats.count(InfoCategory.ABSOLUTE_LINK) == 1


class TestGroupInfoMessages:
    """Tests for group_info_messages function."""

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
        assert len(groups[InfoCategory.NO_GIT_LOGS]) == 1

    def test_returns_empty_dict_for_empty_input(self) -> None:
        groups = group_info_messages([])
        assert groups == {}

    def test_preserves_order_within_category(self) -> None:
        messages = [
            InfoMessage(category=InfoCategory.MISSING_NAV, file="first.md"),
            InfoMessage(category=InfoCategory.MISSING_NAV, file="second.md"),
            InfoMessage(category=InfoCategory.MISSING_NAV, file="third.md"),
        ]
        groups = group_info_messages(messages)

        assert len(groups[InfoCategory.MISSING_NAV]) == 3
        assert groups[InfoCategory.MISSING_NAV][0].file == "first.md"
        assert groups[InfoCategory.MISSING_NAV][1].file == "second.md"
        assert groups[InfoCategory.MISSING_NAV][2].file == "third.md"

    def test_groups_all_categories(self) -> None:
        messages = [
            InfoMessage(category=InfoCategory.BROKEN_LINK, file="a.md", target="x"),
            InfoMessage(category=InfoCategory.ABSOLUTE_LINK, file="b.md", target="/y"),
            InfoMessage(category=InfoCategory.UNRECOGNIZED_LINK, file="c.md", target="z"),
            InfoMessage(category=InfoCategory.MISSING_NAV, file="d.md"),
            InfoMessage(category=InfoCategory.NO_GIT_LOGS, file="e.md"),
        ]
        groups = group_info_messages(messages)

        assert len(groups) == 5
        for cat in InfoCategory:
            assert cat in groups
            assert len(groups[cat]) == 1

    def test_single_message_creates_single_group(self) -> None:
        messages = [
            InfoMessage(category=InfoCategory.BROKEN_LINK, file="only.md", target="missing.md"),
        ]
        groups = group_info_messages(messages)

        assert len(groups) == 1
        assert InfoCategory.BROKEN_LINK in groups
        assert groups[InfoCategory.BROKEN_LINK][0].file == "only.md"


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

        # Check that info messages were collected
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

        # First build with info message
        for line in [
            "INFO    -  Building...",
            "INFO    -  Doc file 'docs/index.md' contains a link 'old.md', but the target is not found.",
            "INFO    -  Documentation built in 1.00 seconds",
            "INFO    -  Serving on http://127.0.0.1:8000/",
        ]:
            processor.process_line(line)

        assert len(processor.all_info_messages) == 1
        assert processor.all_info_messages[0].target == "old.md"

        # Rebuild with different info message
        for line in [
            "INFO    -  Detected file changes",
            "INFO    -  Building...",
            "INFO    -  Doc file 'docs/page.md' contains a link 'new.md', but the target is not found.",
            "INFO    -  Documentation built in 0.50 seconds",
        ]:
            processor.process_line(line)

        processor.finalize()

        # Should only have the new message after rebuild
        assert len(processor.all_info_messages) == 1
        assert processor.all_info_messages[0].target == "new.md"

    def test_handles_multiple_info_messages_in_single_build(self) -> None:
        console = Console(force_terminal=False, no_color=True, width=80)

        processor = StreamingProcessor(
            console=console,
            verbose=False,
            errors_only=False,
        )

        lines = [
            "INFO    -  Building documentation...",
            'INFO    -  The following pages exist in the docs directory, but are not included in the "nav" configuration:',
            "  - orphan1.md",
            "  - orphan2.md",
            "[git-revision-date-localized-plugin] 'docs/draft.md' has no git logs",
            "INFO    -  Doc file 'docs/index.md' contains a link 'missing.md', but the target is not found.",
            "INFO    -  Doc file 'docs/api.md' contains an absolute link '/users', it was left as is.",
            "INFO    -  Documentation built in 1.50 seconds",
        ]

        for line in lines:
            processor.process_line(line)

        processor.finalize()

        # Should have: 2 missing nav + 1 no git logs + 1 broken link + 1 absolute link = 5
        assert len(processor.all_info_messages) == 5

        groups = group_info_messages(processor.all_info_messages)
        assert len(groups[InfoCategory.MISSING_NAV]) == 2
        assert len(groups[InfoCategory.NO_GIT_LOGS]) == 1
        assert len(groups[InfoCategory.BROKEN_LINK]) == 1
        assert len(groups[InfoCategory.ABSOLUTE_LINK]) == 1
