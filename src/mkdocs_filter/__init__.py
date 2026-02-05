"""Filter mkdocs build output to show only warnings and errors with nice formatting.

Usage:
    mkdocs build 2>&1 | mkdocs-filter
    mkdocs serve 2>&1 | mkdocs-filter -v
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from enum import Enum

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

__version__ = "0.1.0"


class Level(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass
class Issue:
    level: Level
    source: str
    message: str
    file: str | None = None
    code: str | None = None
    output: str | None = None


@dataclass
class BuildInfo:
    """Information extracted from the build output."""

    server_url: str | None = None
    build_dir: str | None = None
    build_time: str | None = None


def extract_build_info(lines: list[str]) -> BuildInfo:
    """Extract server URL, build directory, and timing from mkdocs output."""
    info = BuildInfo()
    for line in lines:
        # Server URL: "Serving on http://127.0.0.1:8000/"
        if match := re.search(r"Serving on (https?://\S+)", line):
            info.server_url = match.group(1)
        # Build time: "Documentation built in 78.99 seconds"
        if match := re.search(r"Documentation built in ([\d.]+) seconds", line):
            info.build_time = match.group(1)
        # Build directory from site_dir config or default
        if match := re.search(r"Building documentation to directory: (.+)", line):
            info.build_dir = match.group(1).strip()
    return info


def parse_mkdocs_output(lines: list[str]) -> list[Issue]:
    """Parse mkdocs output and extract warnings/errors."""
    issues = []
    i = 0
    # Track lines that are part of markdown_exec output to skip them
    skip_until = -1

    while i < len(lines):
        if i < skip_until:
            i += 1
            continue

        line = lines[i]

        # Match WARNING or ERROR lines
        if "WARNING" in line or "ERROR" in line:
            # Determine level
            level = Level.ERROR if "ERROR" in line else Level.WARNING

            # Check if this is a markdown_exec error with code block
            if "markdown_exec" in line:
                issue, end_idx = parse_markdown_exec_issue(lines, i, level)
                if issue:
                    issues.append(issue)
                    skip_until = end_idx
                    i = end_idx
                    continue

            # Skip lines that look like they're part of a traceback
            stripped = line.strip()
            if stripped.startswith("raise ") or stripped.startswith("File "):
                i += 1
                continue

            # Regular warning/error
            message = line
            message = re.sub(r"^\[stderr\]\s*", "", message)
            message = re.sub(r"^\d{4}-\d{2}-\d{2}.*?-\s*", "", message)
            message = re.sub(r"^(WARNING|ERROR)\s*-?\s*", "", message)

            if message.strip():
                # Try to extract file path from message
                file_path = None
                if file_match := re.search(r"'([^']+\.md)'", message):
                    file_path = file_match.group(1)
                elif file_match := re.search(r'"([^"]+\.md)"', message):
                    file_path = file_match.group(1)

                issues.append(
                    Issue(level=level, source="mkdocs", message=message.strip(), file=file_path)
                )

        i += 1

    return issues


def parse_markdown_exec_issue(
    lines: list[str], start: int, level: Level
) -> tuple[Issue | None, int]:
    """Parse a markdown_exec warning/error block. Returns (issue, end_index)."""
    # Look backwards to find which file was being processed
    file_path = None
    for j in range(start - 1, max(-1, start - 50), -1):
        prev_line = lines[j]
        # Look for verbose mode "Reading: file.md" message (most reliable)
        if match := re.search(r"DEBUG\s*-\s*Reading:\s*(\S+\.md)", prev_line):
            file_path = match.group(1)
            break
        # Look for breadcrumb that mentions the file
        if match := re.search(r"Generated breadcrumb string:.*\[([^\]]+)\]\(/([^)]+)\)", prev_line):
            potential_file = match.group(2) + ".md"
            file_path = potential_file
            break
        # Or Doc file message
        if match := re.search(r"Doc file '([^']+\.md)'", prev_line):
            file_path = match.group(1)
            break

    # Collect the code block and output sections
    code_lines = []
    output_lines = []
    in_code = False
    in_output = False
    session_info = None
    line_number = None

    i = start + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect section markers
        if stripped == "Code block is:":
            in_code = True
            in_output = False
            i += 1
            continue
        if stripped == "Output is:":
            in_code = False
            in_output = True
            i += 1
            continue

        # Stop conditions: new log line
        if stripped and not line.startswith("  ") and not line.startswith("\t"):
            if re.match(r"^(INFO|WARNING|ERROR)\s*-", stripped):
                break
            if re.match(r"^\d{4}-\d{2}-\d{2}", stripped):
                break
            if re.match(r"^\[stderr\]", stripped):
                break

        # Collect content
        if in_code and stripped:
            code_lines.append(line.rstrip())
        elif in_output and stripped:
            output_lines.append(line.rstrip())
            # Extract session and line info from traceback
            if match := re.search(
                r'File "<code block: session ([^;]+); n(\d+)>", line (\d+)', stripped
            ):
                session_info = match.group(1)
                line_number = match.group(3)

        i += 1

    # Find the actual error message
    error_msg = "Code execution failed"
    for line in reversed(output_lines):
        line = line.strip()
        if line and ("Error:" in line or "Exception:" in line) and not line.startswith("File "):
            error_msg = line
            break

    # Build location string
    location_parts = []
    if file_path:
        location_parts.append(file_path)
    if session_info:
        location_parts.append(f"session '{session_info}'")
    if line_number:
        location_parts.append(f"line {line_number}")

    return (
        Issue(
            level=level,
            source="markdown_exec",
            message=error_msg,
            file=" → ".join(location_parts) if location_parts else None,
            code="\n".join(code_lines) if code_lines else None,
            output="\n".join(output_lines) if output_lines else None,
        ),
        i,
    )


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


def print_issue(console: Console, issue: Issue, verbose: bool = False) -> None:
    """Print an issue with rich formatting."""
    style = "red bold" if issue.level == Level.ERROR else "yellow bold"
    icon = "✗" if issue.level == Level.ERROR else "⚠"

    # Header
    header = Text()
    header.append(f"{icon} ", style=style)
    header.append(f"{issue.level.value}", style=style)
    header.append(f" [{issue.source}] ", style="dim")
    header.append(issue.message)
    console.print(header)

    # Show file/location if available
    if issue.file:
        console.print(f"   📍 {issue.file}", style="cyan")

    # For markdown_exec issues, always show code (truncated if not verbose)
    if issue.code:
        console.print()
        code_to_show = issue.code

        # In non-verbose mode, show last 10 lines of code
        if not verbose:
            code_lines = issue.code.split("\n")
            if len(code_lines) > 10:
                code_to_show = f"  # ... ({len(code_lines) - 10} lines above)\n" + "\n".join(
                    code_lines[-10:]
                )

        code_to_show = dedent_code(code_to_show)

        syntax = Syntax(
            code_to_show,
            "python",
            theme="monokai",
            line_numbers=True,
            word_wrap=True,
        )
        console.print(Panel(syntax, title="Code Block", border_style="cyan", expand=False))

    # Show output/traceback in verbose mode
    if verbose and issue.output:
        output_lines = issue.output.split("\n")
        if len(output_lines) > 15:
            output_text = "\n".join(output_lines[-15:])
            output_text = f"... ({len(output_lines) - 15} lines omitted)\n" + output_text
        else:
            output_text = issue.output

        output_text = dedent_code(output_text)
        console.print(Panel(output_text, title="Traceback", border_style="red", expand=False))

    console.print()


def main() -> int:
    """Main entry point for the CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Filter mkdocs output to show only warnings and errors",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    mkdocs build --verbose 2>&1 | mkdocs-filter
    mkdocs build --verbose 2>&1 | mkdocs-filter -v
    mkdocs serve 2>&1 | mkdocs-filter
    mkdocs build 2>&1 | mkdocs-filter --errors-only

Note: Use --verbose with mkdocs to get file paths for code block errors.
        """,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show full code blocks and tracebacks for markdown_exec issues",
    )
    parser.add_argument(
        "-e", "--errors-only", action="store_true", help="Show only errors, not warnings"
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress spinner")
    parser.add_argument(
        "--raw", action="store_true", help="Pass through raw mkdocs output without filtering"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    # Raw mode - just pass through everything
    if args.raw:
        for line in sys.stdin:
            print(line, end="")
        return 0

    # When piped, Rich may not detect terminal width properly
    console = Console(
        force_terminal=not args.no_color,
        no_color=args.no_color,
        width=120 if sys.stdin.isatty() is False else None,
        soft_wrap=True,
    )

    # Read input with progress spinner (unless disabled)
    lines: list[str] = []

    def truncate_line(line: str, max_len: int = 60) -> str:
        """Truncate line for display, keeping useful part."""
        line = line.strip()
        line = re.sub(r"^\[stderr\]\s*", "", line)
        line = re.sub(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+\s*-\s*", "", line)
        line = re.sub(r"^[\w.]+\s*-\s*(INFO|WARNING|ERROR)\s*-\s*", "", line)
        if len(line) > max_len:
            return line[:max_len] + "..."
        return line

    if args.no_progress or args.no_color:
        lines = [line.rstrip() for line in sys.stdin]
    else:
        from rich.live import Live
        from rich.spinner import Spinner

        with Live(console=console, refresh_per_second=10, transient=True) as live:
            for line in sys.stdin:
                lines.append(line.rstrip())
                display_line = truncate_line(line)
                spinner = Spinner("dots", text=f" Building... {display_line}", style="cyan")
                live.update(spinner)

    # Extract build info
    build_info = extract_build_info(lines)

    # Parse issues
    issues = parse_mkdocs_output(lines)

    # Filter if errors-only
    if args.errors_only:
        issues = [i for i in issues if i.level == Level.ERROR]

    # Deduplicate
    seen: set[tuple[Level, str]] = set()
    unique_issues: list[Issue] = []
    for issue in issues:
        key = (issue.level, issue.message[:100])
        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)

    # Print summary header
    error_count = sum(1 for i in unique_issues if i.level == Level.ERROR)
    warning_count = sum(1 for i in unique_issues if i.level == Level.WARNING)

    if not unique_issues:
        console.print("[green]✓ No warnings or errors[/green]")
    else:
        console.print()
        for issue in unique_issues:
            print_issue(console, issue, verbose=args.verbose)

        console.print("─" * 40, style="dim")
        summary = Text("Summary: ")
        if error_count:
            summary.append(f"{error_count} error(s)", style="red bold")
            if warning_count:
                summary.append(", ")
        if warning_count:
            summary.append(f"{warning_count} warning(s)", style="yellow bold")
        console.print(summary)

    # Always show build info at the end
    console.print()
    if build_info.server_url:
        console.print(f"[bold green]🌐 Server:[/bold green] {build_info.server_url}")
    if build_info.build_dir:
        console.print(f"[bold blue]📁 Output:[/bold blue] {build_info.build_dir}")
    if build_info.build_time:
        console.print(f"[dim]Built in {build_info.build_time}s[/dim]")

    # Show hint for seeing more details
    if unique_issues:
        console.print()
        hints = []
        if not args.verbose:
            hints.append("[dim]-v[/dim] for verbose output")
        hints.append("[dim]--raw[/dim] for full mkdocs output")
        console.print(f"[dim]Hint: {', '.join(hints)}[/dim]")

        # Check if any markdown_exec issues are missing file context
        # (has session info but no .md file path)
        missing_file_context = any(
            i.source == "markdown_exec" and i.file and "session" in i.file and ".md" not in i.file
            for i in unique_issues
        )
        if missing_file_context:
            console.print(
                "[dim]Tip: Use [/dim][dim italic]mkdocs build --verbose[/dim italic]"
                "[dim] to see which file contains code block errors[/dim]"
            )

    return 1 if error_count else 0


if __name__ == "__main__":
    sys.exit(main())
