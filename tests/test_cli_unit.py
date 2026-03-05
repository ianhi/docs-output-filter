"""Unit tests for cli.py main() function.

Tests the main() entry point's argument parsing, mode dispatch logic,
console configuration, and error handling. Uses mocking for mode dispatch
verification and real stdin/stdout for end-to-end integration tests.

Key test areas:
- Mode dispatch (streaming, batch, interactive, URL, wrap, MCP)
- Raw mode passthrough
- Console width configuration
- KeyboardInterrupt handling
- Version display
- Exit codes
"""

import io
from unittest.mock import MagicMock, patch

import pytest

from docs_output_filter.cli import __version__, main


class TestModeDispatch:
    """Tests for mode selection and dispatch logic."""

    def test_streaming_mode_dispatch_default(self, monkeypatch) -> None:
        """Default mode should dispatch to streaming (no --batch)."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO("INFO - test\n"))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.return_value = 0
            exit_code = main()

        mock_streaming.assert_called_once()
        assert exit_code == 0

    def test_batch_mode_dispatch(self, monkeypatch) -> None:
        """--batch flag should dispatch to batch mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--batch", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO("INFO - test\n"))

        with patch("docs_output_filter.cli.run_batch_mode") as mock_batch:
            mock_batch.return_value = 0
            exit_code = main()

        mock_batch.assert_called_once()
        assert exit_code == 0

    def test_streaming_flag_explicit(self, monkeypatch) -> None:
        """--streaming flag should explicitly enable streaming mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--streaming", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO("INFO - test\n"))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.return_value = 0
            exit_code = main()

        mock_streaming.assert_called_once()
        assert exit_code == 0

    def test_url_mode_dispatch(self, monkeypatch) -> None:
        """--url flag should dispatch to URL mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--url", "http://example.com/log"])

        with patch("docs_output_filter.cli.run_url_mode") as mock_url:
            mock_url.return_value = 0
            exit_code = main()

        mock_url.assert_called_once()
        assert exit_code == 0

    def test_interactive_mode_dispatch(self, monkeypatch) -> None:
        """--interactive/-i flag should dispatch to interactive mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "-i"])
        monkeypatch.setattr("sys.stdin", io.StringIO("INFO - test\n"))

        with patch("docs_output_filter.cli.run_interactive_mode") as mock_interactive:
            mock_interactive.return_value = 0
            exit_code = main()

        mock_interactive.assert_called_once()
        assert exit_code == 0

    def test_wrap_mode_dispatch_with_double_dash(self, monkeypatch) -> None:
        """Wrapper mode (-- command) should dispatch to wrap mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--", "echo", "test"])

        with patch("docs_output_filter.cli.run_wrap_mode") as mock_wrap:
            mock_wrap.return_value = 0
            exit_code = main()

        mock_wrap.assert_called_once()
        # Verify command is passed without the '--'
        call_args = mock_wrap.call_args
        assert call_args[0][2] == ["echo", "test"]  # wrap_command argument
        assert exit_code == 0

    def test_wrap_mode_dispatch_without_double_dash(self, monkeypatch) -> None:
        """Wrapper mode should work without -- if command doesn't start with -."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "echo", "test"])

        with patch("docs_output_filter.cli.run_wrap_mode") as mock_wrap:
            mock_wrap.return_value = 0
            exit_code = main()

        mock_wrap.assert_called_once()
        call_args = mock_wrap.call_args
        assert call_args[0][2] == ["echo", "test"]
        assert exit_code == 0

    def test_mcp_mode_dispatch_watch(self, monkeypatch) -> None:
        """--mcp --watch should dispatch to MCP server in watch mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--mcp", "--watch"])

        with patch("docs_output_filter.mcp_server.run_mcp_server") as mock_mcp:
            mock_mcp.return_value = 0
            exit_code = main()

        mock_mcp.assert_called_once_with(
            project_dir=None, pipe_mode=False, watch_mode=True, state_dir=None
        )
        assert exit_code == 0

    def test_mcp_mode_dispatch_project_dir(self, monkeypatch) -> None:
        """--mcp --project-dir should dispatch to MCP server with project dir."""
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--mcp", "--project-dir", "/path/to/proj"]
        )

        with patch("docs_output_filter.mcp_server.run_mcp_server") as mock_mcp:
            mock_mcp.return_value = 0
            exit_code = main()

        mock_mcp.assert_called_once_with(
            project_dir="/path/to/proj", pipe_mode=False, watch_mode=False, state_dir=None
        )
        assert exit_code == 0

    def test_mcp_mode_dispatch_pipe(self, monkeypatch) -> None:
        """--mcp --pipe should dispatch to MCP server in pipe mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--mcp", "--pipe"])

        with patch("docs_output_filter.mcp_server.run_mcp_server") as mock_mcp:
            mock_mcp.return_value = 0
            exit_code = main()

        mock_mcp.assert_called_once_with(
            project_dir=None, pipe_mode=True, watch_mode=False, state_dir=None
        )
        assert exit_code == 0


class TestRawMode:
    """Tests for --raw flag passthrough behavior."""

    def test_raw_mode_passes_through_unchanged(self, monkeypatch) -> None:
        """--raw should pass all input directly to stdout."""
        input_text = "INFO - Building\nDEBUG - Details\nWARNING - Issue\n"
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--raw"])
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        captured_output = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured_output)

        exit_code = main()

        assert exit_code == 0
        assert captured_output.getvalue() == input_text

    def test_raw_mode_preserves_formatting(self, monkeypatch) -> None:
        """--raw should preserve exact formatting including whitespace."""
        input_text = "  WARNING -  Indented\n\n\nMultiple blank lines\n"
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--raw"])
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        captured_output = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured_output)

        exit_code = main()

        assert exit_code == 0
        assert captured_output.getvalue() == input_text

    def test_raw_mode_with_no_input(self, monkeypatch) -> None:
        """--raw should handle empty input gracefully."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--raw"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        captured_output = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured_output)

        exit_code = main()

        assert exit_code == 0
        assert captured_output.getvalue() == ""


class TestKeyboardInterrupt:
    """Tests for KeyboardInterrupt handling."""

    def test_keyboard_interrupt_returns_130(self, monkeypatch) -> None:
        """KeyboardInterrupt should return exit code 130."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO("INFO - test\n"))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.side_effect = KeyboardInterrupt()

            captured_stderr = io.StringIO()
            monkeypatch.setattr("sys.stderr", captured_stderr)

            exit_code = main()

        assert exit_code == 130
        assert "Interrupted" in captured_stderr.getvalue()

    def test_keyboard_interrupt_in_batch_mode(self, monkeypatch) -> None:
        """KeyboardInterrupt should work in any mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--batch", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO("INFO - test\n"))

        with patch("docs_output_filter.cli.run_batch_mode") as mock_batch:
            mock_batch.side_effect = KeyboardInterrupt()

            captured_stderr = io.StringIO()
            monkeypatch.setattr("sys.stderr", captured_stderr)

            exit_code = main()

        assert exit_code == 130

    def test_keyboard_interrupt_message_format(self, monkeypatch) -> None:
        """KeyboardInterrupt message should include newlines."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.side_effect = KeyboardInterrupt()

            captured_stderr = io.StringIO()
            monkeypatch.setattr("sys.stderr", captured_stderr)

            main()

        stderr_output = captured_stderr.getvalue()
        assert stderr_output.startswith("\n\n")
        assert "Interrupted." in stderr_output


class TestConsoleConfiguration:
    """Tests for Console width and color configuration."""

    def test_console_width_when_piping(self, monkeypatch) -> None:
        """Console width should be 120 when piping (stdin not a tty)."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--no-progress"])

        # Mock stdin as non-tty (piped)
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.readline.return_value = ""  # Empty input
        monkeypatch.setattr("sys.stdin", mock_stdin)

        with patch("docs_output_filter.cli.Console") as MockConsole:
            mock_console_instance = MagicMock()
            MockConsole.return_value = mock_console_instance

            with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
                mock_streaming.return_value = 0
                main()

            # Verify Console was created with width=120
            MockConsole.assert_called_once()
            call_kwargs = MockConsole.call_args[1]
            assert call_kwargs["width"] == 120

    def test_console_width_when_wrapping(self, monkeypatch) -> None:
        """Console width should be None when using wrapper mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--", "echo", "test"])

        with patch("docs_output_filter.cli.Console") as MockConsole:
            mock_console_instance = MagicMock()
            MockConsole.return_value = mock_console_instance

            with patch("docs_output_filter.cli.run_wrap_mode") as mock_wrap:
                mock_wrap.return_value = 0
                main()

            # Verify Console was created with width=None
            MockConsole.assert_called_once()
            call_kwargs = MockConsole.call_args[1]
            assert call_kwargs["width"] is None

    def test_console_width_default(self, monkeypatch) -> None:
        """Console width should be None when stdin is a tty."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--no-progress"])

        # Mock stdin as tty
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdin.readline.return_value = ""
        monkeypatch.setattr("sys.stdin", mock_stdin)

        with patch("docs_output_filter.cli.Console") as MockConsole:
            mock_console_instance = MagicMock()
            MockConsole.return_value = mock_console_instance

            with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
                mock_streaming.return_value = 0
                main()

            MockConsole.assert_called_once()
            call_kwargs = MockConsole.call_args[1]
            assert call_kwargs["width"] is None

    def test_console_no_color_flag(self, monkeypatch) -> None:
        """--no-color should configure Console with no_color=True."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--no-color", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.Console") as MockConsole:
            mock_console_instance = MagicMock()
            MockConsole.return_value = mock_console_instance

            with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
                mock_streaming.return_value = 0
                main()

            MockConsole.assert_called_once()
            call_kwargs = MockConsole.call_args[1]
            assert call_kwargs["no_color"] is True
            assert call_kwargs["force_terminal"] is False

    def test_console_color_enabled_by_default(self, monkeypatch) -> None:
        """Without --no-color, console should have color enabled."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.Console") as MockConsole:
            mock_console_instance = MagicMock()
            MockConsole.return_value = mock_console_instance

            with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
                mock_streaming.return_value = 0
                main()

            MockConsole.assert_called_once()
            call_kwargs = MockConsole.call_args[1]
            assert call_kwargs["no_color"] is False
            assert call_kwargs["force_terminal"] is True


class TestBatchModeSpinnerConfiguration:
    """Tests for batch mode spinner configuration."""

    def test_batch_mode_show_spinner_default(self, monkeypatch) -> None:
        """Batch mode should show spinner by default."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--batch"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_batch_mode") as mock_batch:
            mock_batch.return_value = 0
            main()

        mock_batch.assert_called_once()
        call_kwargs = mock_batch.call_args[1]
        assert call_kwargs["show_spinner"] is True

    def test_batch_mode_no_progress_disables_spinner(self, monkeypatch) -> None:
        """--no-progress should disable spinner in batch mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--batch", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_batch_mode") as mock_batch:
            mock_batch.return_value = 0
            main()

        mock_batch.assert_called_once()
        call_kwargs = mock_batch.call_args[1]
        assert call_kwargs["show_spinner"] is False

    def test_batch_mode_no_color_disables_spinner(self, monkeypatch) -> None:
        """--no-color should disable spinner in batch mode."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--batch", "--no-color"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_batch_mode") as mock_batch:
            mock_batch.return_value = 0
            main()

        mock_batch.assert_called_once()
        call_kwargs = mock_batch.call_args[1]
        assert call_kwargs["show_spinner"] is False


class TestVersionFlag:
    """Tests for --version flag."""

    def test_version_flag_displays_version(self, monkeypatch, capsys) -> None:
        """--version should display version and exit."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--version"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert __version__ in captured.out

    def test_version_value(self) -> None:
        """Version should be a non-empty string."""
        assert isinstance(__version__, str)
        assert len(__version__) > 0


class TestEndToEndBatchMode:
    """Integration tests running real batch mode with mocked stdin."""

    def test_batch_mode_processes_warning(self, monkeypatch, capsys) -> None:
        """Batch mode should process warnings from stdin."""
        input_text = "WARNING - Test warning\nINFO - Documentation built in 1.00 seconds\n"
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--batch", "--no-progress", "--no-color"]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "Test warning" in captured.out

    def test_batch_mode_processes_error(self, monkeypatch, capsys) -> None:
        """Batch mode should process errors and return exit code 1."""
        input_text = "ERROR - Build failed\nINFO - Documentation built in 1.00 seconds\n"
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--batch", "--no-progress", "--no-color"]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.out
        assert "Build failed" in captured.out

    def test_batch_mode_no_issues(self, monkeypatch, capsys) -> None:
        """Batch mode should report clean build with no warnings/errors."""
        input_text = "INFO - Building\nINFO - Documentation built in 1.00 seconds\n"
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--batch", "--no-progress", "--no-color"]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No warnings or errors" in captured.out

    def test_batch_mode_deduplicates_warnings(self, monkeypatch, capsys) -> None:
        """Batch mode should deduplicate identical warnings."""
        input_text = (
            "WARNING - Same warning\n"
            "WARNING - Same warning\n"
            "WARNING - Same warning\n"
            "INFO - Documentation built in 1.00 seconds\n"
        )
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--batch", "--no-progress", "--no-color"]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        # Should only show 1 warning, not 3
        assert "1 warning" in captured.out.lower()

    def test_batch_mode_summary_counts(self, monkeypatch, capsys) -> None:
        """Batch mode should show correct summary counts."""
        input_text = (
            "WARNING - Warning 1\n"
            "WARNING - Warning 2\n"
            "ERROR - Error 1\n"
            "INFO - Documentation built in 1.00 seconds\n"
        )
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--batch", "--no-progress", "--no-color"]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        exit_code = main()

        assert exit_code == 1  # Errors present
        captured = capsys.readouterr()
        assert "1 error" in captured.out.lower()
        assert "2 warning" in captured.out.lower()


class TestEndToEndStreamingMode:
    """Integration tests running real streaming mode with mocked stdin."""

    def test_streaming_mode_processes_warning(self, monkeypatch, capsys) -> None:
        """Streaming mode should process warnings incrementally."""
        input_text = (
            "INFO - Building\nWARNING - Test warning\nINFO - Documentation built in 1.00 seconds\n"
        )
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--streaming", "--no-progress", "--no-color"]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "Test warning" in captured.out

    def test_streaming_mode_handles_rebuild(self, monkeypatch, capsys) -> None:
        """Streaming mode should detect and process rebuilds."""
        input_text = (
            "INFO - Building\n"
            "WARNING - First warning\n"
            "INFO - Documentation built in 1.00 seconds\n"
            "INFO - Serving on http://127.0.0.1:8000/\n"
            "INFO - Detected file changes\n"
            "INFO - Building\n"
            "WARNING - Second warning\n"
            "INFO - Documentation built in 0.50 seconds\n"
        )
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--streaming", "--no-progress", "--no-color"]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        # Both warnings should appear
        assert "First warning" in captured.out
        assert "Second warning" in captured.out

    def test_streaming_mode_shows_build_info(self, monkeypatch, capsys) -> None:
        """Streaming mode should extract and display build info."""
        input_text = (
            "INFO - Building documentation to directory: /tmp/site\n"
            "INFO - Documentation built in 2.34 seconds\n"
        )
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--streaming", "--no-progress", "--no-color"]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "/tmp/site" in captured.out
        assert "2.34" in captured.out


class TestArgumentValidation:
    """Tests for argument parsing and validation."""

    def test_errors_only_flag_available(self, monkeypatch) -> None:
        """--errors-only flag should be parsed."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--errors-only", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.return_value = 0
            main()

        # Verify args were passed correctly
        call_args = mock_streaming.call_args[0]
        args = call_args[1]  # Second argument is args
        assert args.errors_only is True

    def test_verbose_flag_available(self, monkeypatch) -> None:
        """--verbose/-v flag should be parsed."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "-v", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.return_value = 0
            main()

        call_args = mock_streaming.call_args[0]
        args = call_args[1]
        assert args.verbose is True

    def test_tool_flag_auto_default(self, monkeypatch) -> None:
        """--tool should default to 'auto'."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.return_value = 0
            main()

        call_args = mock_streaming.call_args[0]
        args = call_args[1]
        assert args.tool == "auto"

    def test_tool_flag_mkdocs(self, monkeypatch) -> None:
        """--tool mkdocs should be accepted."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--tool", "mkdocs", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.return_value = 0
            main()

        call_args = mock_streaming.call_args[0]
        args = call_args[1]
        assert args.tool == "mkdocs"

    def test_tool_flag_sphinx(self, monkeypatch) -> None:
        """--tool sphinx should be accepted."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--tool", "sphinx", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.return_value = 0
            main()

        call_args = mock_streaming.call_args[0]
        args = call_args[1]
        assert args.tool == "sphinx"

    def test_share_state_flag(self, monkeypatch) -> None:
        """--share-state flag should be parsed."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--share-state", "--no-progress"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.return_value = 0
            main()

        call_args = mock_streaming.call_args[0]
        args = call_args[1]
        assert args.share_state is True

    def test_state_dir_flag(self, monkeypatch) -> None:
        """--state-dir flag should accept directory path."""
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--state-dir", "/tmp/state", "--no-progress"]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_streaming_mode") as mock_streaming:
            mock_streaming.return_value = 0
            main()

        call_args = mock_streaming.call_args[0]
        args = call_args[1]
        assert args.state_dir == "/tmp/state"


class TestModePriorityOrder:
    """Tests for mode selection priority when multiple flags are present."""

    def test_mcp_mode_takes_priority(self, monkeypatch) -> None:
        """MCP mode should take priority over other modes."""
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--mcp", "--watch", "--streaming", "--batch"]
        )

        with patch("docs_output_filter.mcp_server.run_mcp_server") as mock_mcp:
            mock_mcp.return_value = 0
            exit_code = main()

        mock_mcp.assert_called_once()
        assert exit_code == 0

    def test_raw_mode_takes_priority_over_streaming(self, monkeypatch) -> None:
        """Raw mode should take priority over streaming/batch."""
        input_text = "WARNING - Should pass through\n"
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--raw", "--streaming"])
        monkeypatch.setattr("sys.stdin", io.StringIO(input_text))

        captured_output = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured_output)

        exit_code = main()

        assert exit_code == 0
        # Should be raw passthrough, not filtered
        assert captured_output.getvalue() == input_text

    def test_wrap_mode_takes_priority_over_streaming(self, monkeypatch) -> None:
        """Wrapper mode should take priority over streaming/batch."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "--streaming", "--", "echo", "test"])

        with patch("docs_output_filter.cli.run_wrap_mode") as mock_wrap:
            mock_wrap.return_value = 0
            exit_code = main()

        mock_wrap.assert_called_once()
        assert exit_code == 0

    def test_url_mode_takes_priority_over_streaming(self, monkeypatch) -> None:
        """URL mode should take priority over streaming/batch."""
        monkeypatch.setattr(
            "sys.argv", ["docs-output-filter", "--url", "http://example.com", "--streaming"]
        )

        with patch("docs_output_filter.cli.run_url_mode") as mock_url:
            mock_url.return_value = 0
            exit_code = main()

        mock_url.assert_called_once()
        assert exit_code == 0

    def test_interactive_mode_takes_priority_over_streaming(self, monkeypatch) -> None:
        """Interactive mode should take priority over streaming/batch."""
        monkeypatch.setattr("sys.argv", ["docs-output-filter", "-i", "--streaming"])
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        with patch("docs_output_filter.cli.run_interactive_mode") as mock_interactive:
            mock_interactive.return_value = 0
            exit_code = main()

        mock_interactive.assert_called_once()
        assert exit_code == 0
