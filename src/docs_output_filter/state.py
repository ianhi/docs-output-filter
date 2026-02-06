"""State file I/O for docs-output-filter.

Handles reading/writing state files shared between the CLI and MCP server.
State is stored in a temp directory (keyed by project path hash) so no files
are created in the project directory and nothing needs to be gitignored.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docs_output_filter.types import (
    BuildInfo,
    InfoCategory,
    InfoMessage,
    Issue,
    Level,
)

STATE_FILE_NAME = "state.json"
# Legacy in-project locations (for migration/cleanup)
OLD_STATE_DIR_NAME = ".mkdocs-output-filter"
LEGACY_STATE_DIR_NAME = ".docs-output-filter"


def find_git_root() -> Path | None:
    """Find the git repository root by looking for .git directory."""
    cwd = Path.cwd()

    for path in [cwd, *cwd.parents]:
        if (path / ".git").exists():
            return path
        if path == Path.home() or path == path.parent:
            break

    return None


def find_project_root() -> Path | None:
    """Find the documentation project root by looking for mkdocs.yml or conf.py."""
    cwd = Path.cwd()

    for path in [cwd, *cwd.parents]:
        if (path / "mkdocs.yml").exists() or (path / "conf.py").exists():
            return path
        if path == Path.home() or path == path.parent:
            break

    return None


def _get_temp_state_dir(project_dir: Path) -> Path:
    """Get temp directory for state file, keyed by project path hash.

    Uses a stable hash of the resolved project path so both CLI and MCP server
    derive the same directory. State lives in /tmp (or platform equivalent),
    so nothing is created in the project directory.
    """
    project_hash = hashlib.sha256(str(project_dir.resolve()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "docs-output-filter" / project_hash


def get_state_file_path(project_dir: Path | None = None) -> Path | None:
    """Get the path to the state file for a project.

    State is stored in a temp directory keyed by project path hash.

    Priority for determining project dir:
    1. Explicit project_dir if provided
    2. Git root (most reliable for cross-directory access)
    3. Current working directory as fallback
    """
    if project_dir is None:
        project_dir = find_git_root()

    if project_dir is None:
        project_dir = Path.cwd()

    return _get_temp_state_dir(project_dir) / STATE_FILE_NAME


def find_state_file() -> Path | None:
    """Search for an existing state file.

    Searches temp directories derived from (in priority order):
    1. Git root (preferred - works across all subdirectories)
    2. Current working directory
    3. Project root (where mkdocs.yml or conf.py is found)

    Also checks legacy in-project locations for migration.

    Returns the path to the first state file found, or None.
    """
    candidates: list[Path] = []

    git_root = find_git_root()
    if git_root:
        candidates.append(git_root)

    candidates.append(Path.cwd())

    project_root = find_project_root()
    if project_root:
        candidates.append(project_root)

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            # Check temp directory (current location)
            state_path = _get_temp_state_dir(resolved) / STATE_FILE_NAME
            if state_path.exists():
                return state_path

            # Fall back to legacy in-project locations
            for legacy_dir in (LEGACY_STATE_DIR_NAME, OLD_STATE_DIR_NAME):
                old_state_path = resolved / legacy_dir / STATE_FILE_NAME
                if old_state_path.exists():
                    return old_state_path
        except OSError:
            continue

    return None


def issue_to_dict(issue: Issue) -> dict[str, Any]:
    """Convert an Issue to a JSON-serializable dict."""
    result: dict[str, Any] = {
        "level": issue.level.value,
        "source": issue.source,
        "message": issue.message,
    }
    if issue.file:
        result["file"] = issue.file
    if issue.line_number is not None:
        result["line_number"] = issue.line_number
    if issue.code:
        result["code"] = issue.code
    if issue.output:
        result["output"] = issue.output
    if issue.warning_code:
        result["warning_code"] = issue.warning_code
    return result


def issue_from_dict(data: dict[str, Any]) -> Issue:
    """Create an Issue from a dict."""
    return Issue(
        level=Level(data["level"]),
        source=data["source"],
        message=data["message"],
        file=data.get("file"),
        line_number=data.get("line_number"),
        code=data.get("code"),
        output=data.get("output"),
        warning_code=data.get("warning_code"),
    )


def build_info_to_dict(info: BuildInfo) -> dict[str, Any]:
    """Convert BuildInfo to a JSON-serializable dict."""
    result: dict[str, Any] = {}
    if info.server_url:
        result["server_url"] = info.server_url
    if info.build_dir:
        result["build_dir"] = info.build_dir
    if info.build_time:
        result["build_time"] = info.build_time
    return result


def build_info_from_dict(data: dict[str, Any]) -> BuildInfo:
    """Create BuildInfo from a dict."""
    return BuildInfo(
        server_url=data.get("server_url"),
        build_dir=data.get("build_dir"),
        build_time=data.get("build_time"),
    )


def info_message_to_dict(msg: InfoMessage) -> dict[str, Any]:
    """Convert an InfoMessage to a JSON-serializable dict."""
    result: dict[str, Any] = {
        "category": msg.category.value,
        "file": msg.file,
    }
    if msg.target:
        result["target"] = msg.target
    if msg.suggestion:
        result["suggestion"] = msg.suggestion
    return result


def info_message_from_dict(data: dict[str, Any]) -> InfoMessage:
    """Create an InfoMessage from a dict."""
    return InfoMessage(
        category=InfoCategory(data["category"]),
        file=data["file"],
        target=data.get("target"),
        suggestion=data.get("suggestion"),
    )


@dataclass
class StateFileData:
    """Data stored in the state file for sharing between CLI and MCP server."""

    issues: list[Issue] = field(default_factory=list)
    info_messages: list[InfoMessage] = field(default_factory=list)
    build_info: BuildInfo = field(default_factory=BuildInfo)
    raw_output: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    project_dir: str | None = None
    build_status: str = "complete"  # "building" or "complete"
    build_started_at: float | None = None  # Timestamp when build started

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "issues": [issue_to_dict(i) for i in self.issues],
            "info_messages": [info_message_to_dict(m) for m in self.info_messages],
            "build_info": build_info_to_dict(self.build_info),
            "raw_output": self.raw_output[-500:],  # Keep last 500 lines
            "timestamp": self.timestamp,
            "project_dir": self.project_dir,
            "build_status": self.build_status,
            "build_started_at": self.build_started_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateFileData:
        """Create from a dict."""
        return cls(
            issues=[issue_from_dict(i) for i in data.get("issues", [])],
            info_messages=[info_message_from_dict(m) for m in data.get("info_messages", [])],
            build_info=build_info_from_dict(data.get("build_info", {})),
            raw_output=data.get("raw_output", []),
            timestamp=data.get("timestamp", 0),
            project_dir=data.get("project_dir"),
            build_status=data.get("build_status", "complete"),
            build_started_at=data.get("build_started_at"),
        )


def write_state_file(
    state: StateFileData,
    project_dir: Path | None = None,
) -> Path | None:
    """Write state to the state file.

    Returns the path to the state file, or None if it couldn't be written.
    """
    state_path = get_state_file_path(project_dir)
    if state_path is None:
        return None

    state_path.parent.mkdir(parents=True, exist_ok=True)

    if project_dir:
        state.project_dir = str(project_dir)
    elif state.project_dir is None:
        root = find_project_root()
        if root:
            state.project_dir = str(root)

    temp_path = state_path.with_suffix(".tmp")
    try:
        with open(temp_path, "w") as f:
            json.dump(state.to_dict(), f, indent=2)
        os.replace(temp_path, state_path)
        return state_path
    except OSError:
        try:
            temp_path.unlink()
        except OSError:
            pass
        return None


def read_state_file(project_dir: Path | None = None) -> StateFileData | None:
    """Read state from the state file.

    If project_dir is specified, reads from that location (temp dir first, then legacy).
    Otherwise, searches for the state file in common locations.

    Returns the state data, or None if the file doesn't exist or can't be read.
    """
    state_path: Path | None
    if project_dir is not None:
        # Check temp directory first (current location)
        state_path = _get_temp_state_dir(project_dir) / STATE_FILE_NAME
        if not state_path.exists():
            # Fall back to legacy in-project locations
            for legacy_dir in (LEGACY_STATE_DIR_NAME, OLD_STATE_DIR_NAME):
                legacy_path = project_dir / legacy_dir / STATE_FILE_NAME
                if legacy_path.exists():
                    state_path = legacy_path
                    break
            else:
                state_path = None
    else:
        state_path = find_state_file()

    if state_path is None or not state_path.exists():
        return None

    try:
        with open(state_path) as f:
            data = json.load(f)
        return StateFileData.from_dict(data)
    except (OSError, json.JSONDecodeError):
        return None


def get_state_file_age(project_dir: Path | None = None) -> float | None:
    """Get the age of the state file in seconds.

    Returns None if the file doesn't exist.
    """
    state = read_state_file(project_dir)
    if state is None:
        return None
    return time.time() - state.timestamp
