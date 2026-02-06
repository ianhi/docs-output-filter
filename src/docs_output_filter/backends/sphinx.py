"""Sphinx backend for docs-output-filter.

Handles parsing of Sphinx and sphinx-autobuild output.
"""

from __future__ import annotations

import re
from collections import defaultdict

from docs_output_filter.backends import BuildTool
from docs_output_filter.types import (
    BuildInfo,
    ChunkBoundary,
    InfoCategory,
    InfoMessage,
    Issue,
    Level,
)


class SphinxBackend:
    """Backend for parsing Sphinx output."""

    tool = BuildTool.SPHINX

    def detect(self, line: str) -> bool:
        """Return True if this line indicates Sphinx output."""
        # Sphinx version line
        if re.match(r"^Running Sphinx v", line):
            return True
        # sphinx-autobuild markers
        if "[sphinx-autobuild]" in line:
            return True
        # Sphinx warning/error format: filepath:line: WARNING: message
        if re.match(r"^.+:\d+: (WARNING|ERROR): ", line):
            return True
        # Sphinx build completion
        if re.match(r"^build (succeeded|finished)", line):
            return True
        # Sphinx build output markers
        if re.match(r"^The HTML pages are in ", line):
            return True
        # Sphinx crash from sphinx-autobuild
        if "Sphinx exited with exit code:" in line:
            return True
        # Sphinx "looking for now-hierarchical" or similar
        if "reading sources..." in line or "writing output..." in line:
            return True
        return False

    def parse_issues(self, lines: list[str]) -> list[Issue]:
        """Parse Sphinx output and extract warnings/errors.

        Handles single-line warnings and multi-line CellExecutionError blocks
        from myst-nb which include tracebacks and cell code.
        """
        issues: list[Issue] = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Sphinx warning/error format: filepath:line: WARNING: message [code]
            match = re.match(r"^(.+?):(\d+): (WARNING|ERROR): (.+)", line)
            if match:
                filepath = match.group(1)
                line_num = int(match.group(2))
                level_str = match.group(3)
                message = match.group(4)
                level = Level.ERROR if level_str == "ERROR" else Level.WARNING
                warning_code = _extract_warning_code(message)
                if warning_code:
                    message = _strip_warning_code(message)

                issues.append(
                    Issue(
                        level=level,
                        source="sphinx",
                        message=message,
                        file=filepath,
                        line_number=line_num,
                        warning_code=warning_code,
                    )
                )
                i += 1
                continue

            # Sphinx warning with file but no line number: "filepath: WARNING: message [code]"
            match = re.match(r"^(.+?): (WARNING|ERROR): (.+)", line)
            if match:
                filepath = match.group(1)
                level_str = match.group(2)
                message = match.group(3)
                level = Level.ERROR if level_str == "ERROR" else Level.WARNING
                warning_code = _extract_warning_code(message)
                if warning_code:
                    message = _strip_warning_code(message)

                # Check for myst-nb CellExecutionError multi-line block
                code = None
                output = None
                if "CellExecutionError" in message:
                    cell_result = _parse_cell_execution_error(lines, i + 1)
                    if cell_result:
                        code = str(cell_result["code"]) if "code" in cell_result else None
                        output = str(cell_result["output"]) if "output" in cell_result else None
                        i = int(cell_result.get("end_index", i + 1))
                        # Extract the actual error type from the output
                        if output:
                            # Last non-empty line of output is the error type
                            error_line = _extract_error_line(output)
                            if error_line and error_line != "CellExecutionError":
                                message = f"Executing notebook failed: {error_line}"

                issues.append(
                    Issue(
                        level=level,
                        source="sphinx",
                        message=message,
                        file=filepath,
                        warning_code=warning_code,
                        code=code,
                        output=output,
                    )
                )
                i += 1
                continue

            # Sphinx warning without file: "WARNING: message"
            match = re.match(r"^(WARNING|ERROR): (.+)", line)
            if match:
                level_str = match.group(1)
                message = match.group(2)
                level = Level.ERROR if level_str == "ERROR" else Level.WARNING
                warning_code = _extract_warning_code(message)
                if warning_code:
                    message = _strip_warning_code(message)

                issues.append(
                    Issue(
                        level=level,
                        source="sphinx",
                        message=message,
                        warning_code=warning_code,
                    )
                )

            i += 1

        return issues

    def parse_info_messages(self, lines: list[str]) -> list[InfoMessage]:
        """Parse INFO-level messages from Sphinx output.

        Handles Python DeprecationWarnings that appear in Sphinx builds.
        These are not Sphinx WARNING/ERROR but Python warning module output.
        """
        messages: list[InfoMessage] = []
        # Track deprecation warnings to group by source package
        deprecation_lines: list[tuple[str, str, str]] = []  # (file, warning_class, message)

        for line in lines:
            # Skip Sphinx WARNING/ERROR lines (handled by parse_issues)
            if re.match(r"^.+?:\d+: (WARNING|ERROR): ", line):
                continue
            if re.match(r"^.+?: (WARNING|ERROR): ", line):
                continue
            if re.match(r"^(WARNING|ERROR): ", line):
                continue

            # Python deprecation warnings: filepath:line: SomeWarning: message
            # CamelCase warning class (not ALL-CAPS like Sphinx's WARNING)
            # Include digits for names like RemovedInSphinx80Warning
            match = re.match(r"^(.+?):(\d+): ([A-Z][a-zA-Z0-9]*Warning): (.+)", line)
            if match:
                filepath = match.group(1)
                warning_class = match.group(3)
                message = match.group(4)

                # Only capture deprecation-like warnings
                if (
                    "Deprecat" in warning_class
                    or "Removed" in warning_class
                    or "Pending" in warning_class
                ):
                    # Extract package name from filepath
                    package = _extract_package_from_path(filepath)
                    deprecation_lines.append((package, warning_class, message))

        # Group deprecation warnings by source package
        if deprecation_lines:
            by_package: dict[str, list[tuple[str, str]]] = defaultdict(list)
            for package, warning_class, message in deprecation_lines:
                by_package[package].append((warning_class, message))

            for package, warnings in by_package.items():
                # Create one InfoMessage per unique (package, message) combo
                seen: set[str] = set()
                for warning_class, message in warnings:
                    key = f"{warning_class}:{message}"
                    if key not in seen:
                        seen.add(key)
                        messages.append(
                            InfoMessage(
                                category=InfoCategory.DEPRECATION_WARNING,
                                file=package,
                                target=warning_class,
                                suggestion=message,
                            )
                        )

        return messages

    def detect_chunk_boundary(self, line: str, prev_line: str | None) -> ChunkBoundary:
        """Detect streaming chunk boundaries in Sphinx output."""
        # Build completion: "build succeeded" or "build finished"
        if re.match(r"^build (succeeded|finished)", line):
            return ChunkBoundary.BUILD_COMPLETE

        # Fallback build completion: "The HTML pages are in ..."
        # This line is on stdout even when "build succeeded" goes to stderr
        if re.match(r"^The HTML pages are in ", line):
            return ChunkBoundary.BUILD_COMPLETE

        # Sphinx crash: "Sphinx exited with exit code: N"
        # (from sphinx-autobuild when sphinx-build fails)
        if "Sphinx exited with exit code:" in line:
            return ChunkBoundary.BUILD_COMPLETE

        # Server started (sphinx-autobuild)
        if re.search(r"Serving on https?://", line):
            return ChunkBoundary.SERVER_STARTED

        # Rebuild detection (sphinx-autobuild)
        if "[sphinx-autobuild]" in line and ("Detected change" in line or "Rebuilding" in line):
            return ChunkBoundary.REBUILD_STARTED

        return ChunkBoundary.NONE

    def extract_build_info(self, lines: list[str]) -> BuildInfo:
        """Extract server URL, build dir, build time from Sphinx output."""
        info = BuildInfo()
        for line in lines:
            # Server URL (sphinx-autobuild): "Serving on http://127.0.0.1:8000"
            if match := re.search(r"Serving on (https?://[^\s\x1b]+)", line):
                info.server_url = match.group(1)
            # Build directory: "The HTML pages are in path."
            if match := re.search(r"The HTML pages are in (.+)\.", line):
                info.build_dir = match.group(1).strip()
            # Warning count: "build succeeded, 5 warnings."
            if match := re.search(r"build (?:succeeded|finished),?\s*(\d+)\s+warnings?", line):
                info.reported_warning_count = int(match.group(1))
            # Build time from "build succeeded in X.Xs"
            if match := re.search(r"build (?:succeeded|finished).*?in\s+([\d.]+)\s*s", line):
                info.build_time = match.group(1)
            # Alternative: "The build finished in X.X sec"
            if match := re.search(r"The build finished in ([\d.]+) sec", line):
                info.build_time = match.group(1)
        return info

    def is_in_multiline_block(self, lines: list[str]) -> bool:
        """Check if buffer is in an unclosed multi-line block.

        Sphinx doesn't have the same multi-line block pattern as mkdocs/markdown_exec,
        so this is simpler.
        """
        return False


def _extract_warning_code(message: str) -> str | None:
    """Extract optional warning code like [toc.not_readable] from end of message."""
    code_match = re.search(r"\[([a-z][a-z0-9_.]+)\]\s*$", message)
    return code_match.group(1) if code_match else None


def _strip_warning_code(message: str) -> str:
    """Remove the [code] suffix from a warning message."""
    return re.sub(r"\s*\[([a-z][a-z0-9_.]+)\]\s*$", "", message).rstrip()


def _parse_cell_execution_error(lines: list[str], start: int) -> dict[str, str | int] | None:
    """Parse a myst-nb CellExecutionError multi-line block.

    Looks for the pattern after a CellExecutionError WARNING line:
        Traceback (most recent call last):
          ...
        nbclient.exceptions.CellExecutionError: An error occurred...
        ------------------
        ...cell code...
        ------------------

        ErrorType

    Returns dict with 'code', 'output', 'end_index' or None if no block found.
    """
    if start >= len(lines):
        return None

    # Look for "Traceback" or "CellExecutionError:" starting the block
    traceback_start = None
    for j in range(start, min(start + 5, len(lines))):
        if lines[j].strip().startswith("Traceback"):
            traceback_start = j
            break
        # Also detect the nbclient error directly
        if "CellExecutionError:" in lines[j]:
            traceback_start = j
            break

    if traceback_start is None:
        return None

    # Collect everything until we find the cell code delimiter "------------------"
    traceback_lines: list[str] = []
    cell_code_lines: list[str] = []
    error_output_lines: list[str] = []
    i = traceback_start
    in_cell_code = False
    found_cell_delimiter = False
    end_index = start

    while i < len(lines):
        line = lines[i]

        # Detect cell code delimiters
        if line.strip() == "------------------":
            if not in_cell_code and not found_cell_delimiter:
                # First delimiter - start of cell code
                in_cell_code = True
                found_cell_delimiter = True
                i += 1
                continue
            elif in_cell_code:
                # Second delimiter - end of cell code
                in_cell_code = False
                i += 1
                # Collect remaining lines as error output (the actual error type)
                while i < len(lines):
                    remaining = lines[i].strip()
                    # Stop at next WARNING, build boundary, or [mystnb marker
                    if re.match(r"^.+?: (WARNING|ERROR): ", lines[i]):
                        break
                    if re.match(r"^(WARNING|ERROR): ", lines[i]):
                        break
                    if remaining.startswith("Versions"):
                        break
                    if remaining.startswith("[sphinx-autobuild]"):
                        break
                    if remaining.startswith("The HTML pages are in"):
                        break
                    if remaining.startswith("build succeeded") or remaining.startswith(
                        "build finished"
                    ):
                        break
                    if remaining.startswith("Sphinx exited with exit code"):
                        break
                    # Collect the error type line(s)
                    if remaining and not re.match(r"^\s*\[mystnb", remaining):
                        error_output_lines.append(remaining)
                    i += 1
                end_index = i
                break

        if in_cell_code:
            cell_code_lines.append(line)
        else:
            traceback_lines.append(line)

        i += 1

    if not found_cell_delimiter and not traceback_lines:
        return None

    result: dict[str, str | int] = {"end_index": end_index}

    if cell_code_lines:
        result["code"] = "\n".join(cell_code_lines)

    # Build the output: traceback + error type
    output_parts: list[str] = []
    if traceback_lines:
        output_parts.extend(traceback_lines)
    if error_output_lines:
        if output_parts:
            output_parts.append("")
        output_parts.extend(error_output_lines)

    if output_parts:
        result["output"] = "\n".join(output_parts)

    return result


def _extract_error_line(output: str) -> str | None:
    """Extract the actual error type from traceback output.

    Looks for the last line that looks like an error name (e.g. 'ValueError',
    'TypeError: message', 'nbclient.exceptions.CellExecutionError: ...').
    """
    for line in reversed(output.split("\n")):
        line = line.strip()
        if not line:
            continue
        # Match "ErrorType" or "ErrorType: message" patterns
        if re.match(r"^[A-Z]\w*(Error|Exception|Warning)", line):
            return line
        # Match "module.ErrorType: message"
        if re.match(r"^[a-z][\w.]*\.[A-Z]\w*(Error|Exception)", line):
            return line.split(":")[-1].strip() if ":" in line else line
    return None


def _extract_package_from_path(filepath: str) -> str:
    """Extract a meaningful package name from a file path.

    For paths like '/path/to/site-packages/somepackage/module.py', extracts 'somepackage'.
    For other paths, returns the parent directory name.
    """
    # Look for site-packages pattern
    match = re.search(r"site-packages/([^/]+)", filepath)
    if match:
        package = match.group(1)
        # Remove version info from .dist-info directories
        package = re.sub(r"[-.]dist-info$", "", package)
        return package

    # Fall back to parent directory
    parts = filepath.replace("\\", "/").split("/")
    if len(parts) >= 2:
        return parts[-2]
    return filepath
