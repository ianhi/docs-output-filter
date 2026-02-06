"""Remote build log fetching for docs-output-filter.

Handles downloading and parsing build logs from remote URLs, with special
support for ReadTheDocs URL auto-transformation.

Key functions:
- fetch_remote_log(): Download a build log from any URL, returns text content
- _transform_readthedocs_url(): Convert ReadTheDocs web UI URLs to raw log API endpoints

Used by both the CLI (run_url_mode) and the MCP server (fetch_build_log tool).

Update this docstring if you add support for new CI/CD platforms or change
the URL transformation logic.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from urllib.error import HTTPError, URLError


def _transform_readthedocs_url(url: str) -> str | None:
    """Transform ReadTheDocs URLs to the raw log endpoint."""
    match = re.match(r"https?://(?:app\.)?readthedocs\.org/projects/[^/]+/builds/(\d+)/?", url)
    if match:
        build_id = match.group(1)
        return f"https://app.readthedocs.org/api/v2/build/{build_id}.txt"

    match = re.match(
        r"https?://(?:app\.)?readthedocs\.org/api/v3/projects/[^/]+/builds/(\d+)/?", url
    )
    if match:
        build_id = match.group(1)
        return f"https://app.readthedocs.org/api/v2/build/{build_id}.txt"

    return None


def fetch_remote_log(url: str) -> str | None:
    """Fetch build log from a remote URL."""
    try:
        rtd_url = _transform_readthedocs_url(url)
        if rtd_url:
            url = rtd_url

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "docs-output-filter/0.1.0",
                "Accept": "text/plain, text/html, application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            content: str = response.read().decode("utf-8")
            if response.headers.get("Content-Type", "").startswith("application/json"):
                try:
                    data = json.loads(content)
                    for key in ["output", "log", "logs", "build_log", "stdout", "stderr"]:
                        if key in data:
                            value = data[key]
                            if isinstance(value, str):
                                return value
                            if isinstance(value, list):
                                return "\n".join(str(v) for v in value)
                            return str(value)
                except json.JSONDecodeError:
                    pass
            return content

    except HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        return None
    except URLError as e:
        print(f"URL Error: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error fetching URL: {e}", file=sys.stderr)
        return None
