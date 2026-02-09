"""Tests for trivial coverage gaps: __main__.py, types.py edge cases."""

from unittest.mock import patch

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


class TestMainModule:
    """Tests for __main__.py entry point."""

    def test_main_module_runs_main_and_exits(self) -> None:
        """Verify __main__.py calls main() and passes result to sys.exit()."""
        import importlib
        import sys

        import docs_output_filter

        # Remove cached __main__ module so reload triggers fresh import
        sys.modules.pop("docs_output_filter.__main__", None)

        with patch.object(docs_output_filter, "main", return_value=0) as mock_main:
            with patch("sys.exit") as mock_exit:
                importlib.import_module("docs_output_filter.__main__")
                mock_main.assert_called_once()
                mock_exit.assert_called_once_with(0)

    def test_main_module_exits_with_nonzero(self) -> None:
        """Verify __main__.py passes non-zero exit code."""
        import importlib
        import sys

        import docs_output_filter

        sys.modules.pop("docs_output_filter.__main__", None)

        with patch.object(docs_output_filter, "main", return_value=1) as mock_main:
            with patch("sys.exit") as mock_exit:
                importlib.import_module("docs_output_filter.__main__")
                mock_main.assert_called_once()
                mock_exit.assert_called_once_with(1)


class TestDedentCodeEdgeCases:
    """Edge cases for dedent_code not covered by test_parsing.py."""

    def test_all_blank_lines(self) -> None:
        """dedent_code with only blank lines returns original."""
        code = "\n\n\n"
        result = dedent_code(code)
        assert result == code

    def test_single_line_no_indent(self) -> None:
        result = dedent_code("hello")
        assert result == "hello"

    def test_mixed_indent_with_empty(self) -> None:
        code = "    a\n\n    b"
        result = dedent_code(code)
        assert result == "a\n\nb"


class TestChunkBoundaryEnum:
    """Ensure all ChunkBoundary values are accessible."""

    def test_all_values(self) -> None:
        assert ChunkBoundary.BUILD_COMPLETE.value == "build_complete"
        assert ChunkBoundary.SERVER_STARTED.value == "server_started"
        assert ChunkBoundary.REBUILD_STARTED.value == "rebuild_started"
        assert ChunkBoundary.ERROR_BLOCK_END.value == "error_block_end"
        assert ChunkBoundary.NONE.value == "none"


class TestInfoCategoryEnum:
    """Ensure all InfoCategory values are accessible."""

    def test_all_values(self) -> None:
        assert InfoCategory.BROKEN_LINK.value == "broken_link"
        assert InfoCategory.ABSOLUTE_LINK.value == "absolute_link"
        assert InfoCategory.UNRECOGNIZED_LINK.value == "unrecognized_link"
        assert InfoCategory.MISSING_NAV.value == "missing_nav"
        assert InfoCategory.NO_GIT_LOGS.value == "no_git_logs"
        assert InfoCategory.DEPRECATION_WARNING.value == "deprecation_warning"


class TestGroupInfoMessages:
    """Additional edge cases for group_info_messages."""

    def test_multiple_categories(self) -> None:
        messages = [
            InfoMessage(category=InfoCategory.BROKEN_LINK, file="a.md", target="x"),
            InfoMessage(category=InfoCategory.DEPRECATION_WARNING, file="pkg", target="DepWarning"),
            InfoMessage(category=InfoCategory.BROKEN_LINK, file="b.md", target="y"),
            InfoMessage(category=InfoCategory.MISSING_NAV, file="orphan.md"),
        ]
        groups = group_info_messages(messages)
        assert len(groups) == 3
        assert len(groups[InfoCategory.BROKEN_LINK]) == 2
        assert len(groups[InfoCategory.DEPRECATION_WARNING]) == 1
        assert len(groups[InfoCategory.MISSING_NAV]) == 1

    def test_single_message(self) -> None:
        messages = [InfoMessage(category=InfoCategory.NO_GIT_LOGS, file="test.md")]
        groups = group_info_messages(messages)
        assert len(groups) == 1
        assert InfoCategory.NO_GIT_LOGS in groups


class TestIssueFields:
    """Test Issue with warning_code field (types.py line ~51)."""

    def test_warning_code_field(self) -> None:
        issue = Issue(
            level=Level.WARNING,
            source="sphinx",
            message="test",
            warning_code="toc.not_readable",
        )
        assert issue.warning_code == "toc.not_readable"

    def test_reported_warning_count(self) -> None:
        info = BuildInfo(reported_warning_count=5)
        assert info.reported_warning_count == 5

    def test_reported_warning_count_default_none(self) -> None:
        info = BuildInfo()
        assert info.reported_warning_count is None


class TestDedentCodeEmptyString:
    """Test dedent_code with empty string — verifies behavior for edge cases."""

    def test_empty_string_returns_empty(self) -> None:
        """dedent_code('') returns '' (all-blank lines path)."""
        result = dedent_code("")
        assert result == ""

    def test_single_blank_line(self) -> None:
        """dedent_code with single newline (only blank lines)."""
        result = dedent_code("\n")
        assert result == "\n"
