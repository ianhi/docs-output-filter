"""MkDocs backend for docs-output-filter.

Handles parsing of mkdocs build and serve output.
"""

from __future__ import annotations

import re

from docs_output_filter.backends import BuildTool
from docs_output_filter.types import (
    BuildInfo,
    ChunkBoundary,
    InfoCategory,
    InfoMessage,
    Issue,
    Level,
)


class MkDocsBackend:
    """Backend for parsing MkDocs output."""

    tool = BuildTool.MKDOCS

    def detect(self, line: str) -> bool:
        """Return True if this line indicates MkDocs output."""
        # MkDocs log format: "INFO -  ...", "WARNING -  ...", etc.
        if re.match(r"^(INFO|WARNING|ERROR|DEBUG)\s+-", line):
            return True
        # Timestamped MkDocs format
        if re.match(r"^\d{4}-\d{2}-\d{2}.*?(INFO|WARNING|ERROR)", line):
            return True
        # MkDocs-specific markers
        if "Documentation built in" in line:
            return True
        if "Building documentation to directory" in line:
            return True
        return False

    def parse_issues(self, lines: list[str]) -> list[Issue]:
        """Parse mkdocs output and extract warnings/errors."""
        return parse_mkdocs_output(lines)

    def parse_info_messages(self, lines: list[str]) -> list[InfoMessage]:
        """Parse important INFO messages from mkdocs output."""
        return parse_info_messages(lines)

    def detect_chunk_boundary(self, line: str, prev_line: str | None) -> ChunkBoundary:
        """Detect if a line marks a chunk boundary in mkdocs output."""
        return detect_chunk_boundary(line, prev_line)

    def extract_build_info(self, lines: list[str]) -> BuildInfo:
        """Extract server URL, build directory, and timing from mkdocs output."""
        return extract_build_info(lines)

    def is_in_multiline_block(self, lines: list[str]) -> bool:
        """Check if we're currently in a multi-line block."""
        return is_in_multiline_block(lines)


def detect_chunk_boundary(line: str, prev_line: str | None = None) -> ChunkBoundary:
    """Detect if a line marks a chunk boundary."""
    stripped = line.strip()

    # Build completion
    if re.search(r"Documentation built in [\d.]+ seconds", line):
        return ChunkBoundary.BUILD_COMPLETE

    # Server started
    if re.search(r"Serving on https?://", line):
        return ChunkBoundary.SERVER_STARTED

    # Rebuild detection - file changes detected
    if "Detected file changes" in line or "Reloading docs" in line:
        return ChunkBoundary.REBUILD_STARTED

    # Rebuild detection - timestamp with "Building documentation"
    if re.match(r"^\d{4}-\d{2}-\d{2}", stripped) and "Building documentation" in line:
        return ChunkBoundary.REBUILD_STARTED

    # If we see a new INFO/WARNING/ERROR after blank lines following error content
    if prev_line is not None and not prev_line.strip():
        if re.match(r"^(INFO|WARNING|ERROR)\s*-", stripped):
            return ChunkBoundary.ERROR_BLOCK_END
        if re.match(r"^\d{4}-\d{2}-\d{2}.*?(INFO|WARNING|ERROR)", stripped):
            return ChunkBoundary.ERROR_BLOCK_END

    return ChunkBoundary.NONE


def is_in_multiline_block(lines: list[str]) -> bool:
    """Check if we're currently in a multi-line block (like markdown_exec output)."""
    if not lines:
        return False

    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if "markdown_exec" in line and ("WARNING" in line or "ERROR" in line):
            for j in range(i + 1, len(lines)):
                check_line = lines[j].strip()
                if (
                    check_line
                    and not check_line.startswith(" ")
                    and not check_line.startswith("\t")
                ):
                    if re.match(r"^(INFO|WARNING|ERROR)\s*-", check_line):
                        return False
                    if re.match(r"^\d{4}-\d{2}-\d{2}.*?(INFO|WARNING|ERROR)", check_line):
                        return False
            return True
    return False


def extract_build_info(lines: list[str]) -> BuildInfo:
    """Extract server URL, build directory, and timing from mkdocs output."""
    info = BuildInfo()
    for line in lines:
        if match := re.search(r"Serving on (https?://[^\s\x1b]+)", line):
            info.server_url = match.group(1)
        if match := re.search(r"Documentation built in ([\d.]+) seconds", line):
            info.build_time = match.group(1)
        if match := re.search(r"Building documentation to directory: (.+)", line):
            info.build_dir = match.group(1).strip()
    return info


def parse_info_messages(lines: list[str]) -> list[InfoMessage]:
    """Parse important INFO messages that should be shown to the user."""
    messages: list[InfoMessage] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Only process INFO lines (not WARNING/ERROR - those are handled separately)
        if "WARNING" in line or "ERROR" in line:
            i += 1
            continue

        # Pattern: Doc file 'X.md' contains a link 'Y', but the target is not found
        if match := re.search(
            r"Doc file ['\"]([^'\"]+)['\"] contains a link ['\"]([^'\"]+)['\"].*(?:target is not found|not found)",
            line,
        ):
            messages.append(
                InfoMessage(
                    category=InfoCategory.BROKEN_LINK,
                    file=match.group(1),
                    target=match.group(2),
                )
            )
            i += 1
            continue

        # Pattern: Doc file 'X.md' contains an absolute link 'Y', it was left as is
        if match := re.search(
            r"Doc file ['\"]([^'\"]+)['\"] contains an absolute link ['\"]([^'\"]+)['\"].*left as is",
            line,
        ):
            suggestion = None
            if "Did you mean" in line:
                if suggest_match := re.search(r"Did you mean ['\"]([^'\"]+)['\"]", line):
                    suggestion = suggest_match.group(1)
            messages.append(
                InfoMessage(
                    category=InfoCategory.ABSOLUTE_LINK,
                    file=match.group(1),
                    target=match.group(2),
                    suggestion=suggestion,
                )
            )
            i += 1
            continue

        # Pattern: Doc file 'X.md' contains an unrecognized relative link 'Y'
        if match := re.search(
            r"Doc file ['\"]([^'\"]+)['\"] contains an unrecognized relative link ['\"]([^'\"]+)['\"]",
            line,
        ):
            suggestion = None
            if "Did you mean" in line:
                if suggest_match := re.search(r"Did you mean ['\"]([^'\"]+)['\"]", line):
                    suggestion = suggest_match.group(1)
            messages.append(
                InfoMessage(
                    category=InfoCategory.UNRECOGNIZED_LINK,
                    file=match.group(1),
                    target=match.group(2),
                    suggestion=suggestion,
                )
            )
            i += 1
            continue

        # Pattern: [git-revision-date-localized-plugin] 'X.md' has no git logs
        if match := re.search(
            r"\[git-revision-date-localized-plugin\].*['\"]([^'\"]+)['\"].*has no git logs",
            line,
        ):
            messages.append(
                InfoMessage(
                    category=InfoCategory.NO_GIT_LOGS,
                    file=match.group(1),
                )
            )
            i += 1
            continue

        # Pattern: pages not in nav (multi-line block)
        if "pages exist in the docs directory, but are not included" in line:
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if next_line.startswith("- "):
                    file_path = next_line[2:].strip()
                    messages.append(
                        InfoMessage(
                            category=InfoCategory.MISSING_NAV,
                            file=file_path,
                        )
                    )
                    i += 1
                elif next_line and not next_line.startswith("-"):
                    break
                else:
                    i += 1
            continue

        i += 1

    return messages


def parse_mkdocs_output(lines: list[str]) -> list[Issue]:
    """Parse mkdocs output and extract warnings/errors."""
    issues: list[Issue] = []
    i = 0
    skip_until = -1

    while i < len(lines):
        if i < skip_until:
            i += 1
            continue

        line = lines[i]

        if "WARNING" in line or "ERROR" in line:
            level = Level.ERROR if "ERROR" in line else Level.WARNING

            if "markdown_exec" in line:
                issue, end_idx = parse_markdown_exec_issue(lines, i, level)
                if issue:
                    issues.append(issue)
                    skip_until = end_idx
                    i = end_idx
                    continue

            stripped = line.strip()
            if stripped.startswith("raise ") or stripped.startswith("File "):
                i += 1
                continue

            message = line
            message = re.sub(r"^\[stderr\]\s*", "", message)
            message = re.sub(r"^\d{4}-\d{2}-\d{2}.*?-\s*", "", message)
            message = re.sub(r"^(WARNING|ERROR)\s*-?\s*", "", message)

            if message.strip():
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
    file_path = None
    for j in range(start - 1, max(-1, start - 50), -1):
        prev_line = lines[j]
        if match := re.search(r"DEBUG\s*-\s*Reading:\s*(\S+\.md)", prev_line):
            file_path = match.group(1)
            break
        if match := re.search(r"Generated breadcrumb string:.*\[([^\]]+)\]\(/([^)]+)\)", prev_line):
            potential_file = match.group(2) + ".md"
            file_path = potential_file
            break
        if match := re.search(r"Doc file '([^']+\.md)'", prev_line):
            file_path = match.group(1)
            break

    code_lines: list[str] = []
    output_lines: list[str] = []
    in_code = False
    in_output = False
    session_info = None
    line_number = None

    i = start + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

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

        if re.match(r"^(INFO|DEBUG|WARNING|ERROR)\s*-", stripped):
            break
        if re.match(r"^\d{4}-\d{2}-\d{2}", stripped):
            break
        if re.match(r"^\[stderr\]", stripped):
            break

        if in_code and stripped:
            code_lines.append(line.rstrip())
        elif in_output and stripped:
            output_lines.append(line.rstrip())
            if match := re.search(
                r'File "<code block: session ([^;]+); n(\d+)>", line (\d+)', stripped
            ):
                session_info = match.group(1)
                line_number = match.group(3)

        i += 1

    error_msg: str = "Code execution failed"
    for line in reversed(output_lines):
        line = line.strip()
        if line and ("Error:" in line or "Exception:" in line) and not line.startswith("File "):
            error_msg = line
            break

    location_parts: list[str] = []
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
