"""Command-line interface and argument parsing for docs-output-filter.

Contains the main() entry point which parses CLI arguments and dispatches
to the appropriate run mode (streaming, batch, interactive, URL, wrap, MCP).

This is the entry point called by the `docs-output-filter` console script
and by `python -m docs_output_filter`.

Key function:
- main(): Parse args, select mode, return exit code

Update this docstring if you add new CLI flags, new run modes, or change
the argument parsing logic.
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from docs_output_filter.modes import (
    run_batch_mode,
    run_interactive_mode,
    run_streaming_mode,
    run_url_mode,
    run_wrap_mode,
)

__version__ = "0.1.0"


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Filter documentation build output to show only warnings and errors (MkDocs, Sphinx)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Wrapper mode (recommended) — runs the command for you, no 2>&1 needed
    docs-output-filter -- mkdocs serve --livereload
    docs-output-filter -- sphinx-autobuild docs docs/_build/html
    docs-output-filter -v -- mkdocs build --verbose

    # Pipe mode — traditional Unix pipe (may need 2>&1)
    mkdocs build --verbose 2>&1 | docs-output-filter
    sphinx-build docs build 2>&1 | docs-output-filter

    # Fetch and process remote build log (e.g., ReadTheDocs)
    docs-output-filter --url https://readthedocs.org/api/v3/projects/myproject/builds/123/

    # MCP server mode (for code agents)
    docs-output-filter --mcp --watch
    docs-output-filter --mcp --project-dir /path/to/project

Note: Use --verbose with mkdocs to get file paths for code block errors.
        """,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show full code blocks and tracebacks",
    )
    parser.add_argument(
        "-e", "--errors-only", action="store_true", help="Show only errors, not warnings"
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress spinner")
    parser.add_argument(
        "--raw", action="store_true", help="Pass through raw build output without filtering"
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Enable streaming mode (processes output incrementally)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Force batch mode (wait for all input before processing)",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Interactive mode: toggle between filtered/raw with keyboard (r=raw, f=filtered, q=quit)",
    )
    parser.add_argument(
        "--tool",
        choices=["mkdocs", "sphinx", "auto"],
        default="auto",
        help="Documentation tool to parse output for (default: auto-detect)",
    )
    parser.add_argument(
        "--share-state",
        action="store_true",
        help="Write state file for MCP server access (stored in temp directory)",
    )
    parser.add_argument(
        "--state-dir",
        type=str,
        help="Directory for state file (default: auto-detect from project root or git root)",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Fetch and process build log from URL (e.g., ReadTheDocs build log)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run as MCP server for code agent integration (use with --project-dir or --watch)",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        help="Project directory for MCP server mode (requires --mcp)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="MCP watch mode: read state file written by --share-state (requires --mcp)",
    )
    parser.add_argument(
        "--pipe",
        action="store_true",
        help="MCP pipe mode: read build output from stdin (requires --mcp)",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run (use -- to separate from options). "
        "Runs the command with unbuffered output and captures stdout+stderr.",
    )
    args = parser.parse_args()

    # MCP server mode - delegate to mcp_server module
    if args.mcp:
        from docs_output_filter.mcp_server import run_mcp_server

        return run_mcp_server(
            project_dir=args.project_dir,
            pipe_mode=args.pipe,
            watch_mode=args.watch,
            state_dir=args.state_dir,
        )

    try:
        # Raw mode - just pass through everything
        if args.raw:
            for line in sys.stdin:
                print(line, end="")
            return 0

        # Parse wrapper command (strip leading '--' if present)
        wrap_command = getattr(args, "command", [])
        if wrap_command and wrap_command[0] == "--":
            wrap_command = wrap_command[1:]

        console = Console(
            force_terminal=not args.no_color,
            no_color=args.no_color,
            width=120 if (not wrap_command and sys.stdin.isatty() is False) else None,
            soft_wrap=True,
        )

        # Wrapper mode - run command as subprocess
        if wrap_command:
            return run_wrap_mode(console, args, wrap_command)

        # URL mode
        if args.url:
            return run_url_mode(console, args)

        # Interactive mode
        if args.interactive:
            return run_interactive_mode(console, args)

        # Determine mode: streaming vs batch
        use_streaming = args.streaming or not args.batch

        if use_streaming:
            return run_streaming_mode(console, args)
        else:
            show_spinner = not args.no_progress and not args.no_color
            return run_batch_mode(console, args, show_spinner=show_spinner)

    except KeyboardInterrupt:
        print("\n\nInterrupted.", file=sys.stderr)
        return 130
