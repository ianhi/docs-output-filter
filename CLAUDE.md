# mkdocs-filter Development Guide

## Project Overview

`mkdocs-filter` is a CLI tool that filters mkdocs build/serve output to show only warnings and errors with nice formatting. It's designed to be piped after mkdocs commands:

```bash
mkdocs build 2>&1 | mkdocs-filter
```

## Key Features

- **Progress spinner** during build with current activity shown
- **Filtered output** showing only WARNING and ERROR level messages
- **Code block display** for markdown_exec errors with syntax highlighting
- **Location info** including file, session name, and line number
- **Build info** at the end (output dir, server URL, build time)
- **Hints** for available flags when issues are found

## Architecture

The tool is a single-file Python package in `src/mkdocs_filter/__init__.py`:

1. **Input**: Reads lines from stdin (piped mkdocs output)
2. **Parsing**: Extracts issues using regex patterns
3. **Output**: Renders with Rich library for nice formatting

### Key Classes

- `Level`: Enum for ERROR/WARNING
- `Issue`: Dataclass holding parsed issue info (level, source, message, file, code, output)
- `BuildInfo`: Dataclass for server URL, build dir, build time

### Key Functions

- `parse_mkdocs_output()`: Main parsing loop, dispatches to specialized parsers
- `parse_markdown_exec_issue()`: Handles markdown_exec code execution errors
- `extract_build_info()`: Extracts server URL, build dir, timing
- `print_issue()`: Renders an issue with Rich formatting

## Current Limitations & Known Issues

1. **File detection**: Uses breadcrumb/Doc file messages to find which file had the error, which is fragile
2. **No tests**: Need comprehensive test suite
3. **markdown_exec only**: Other mkdocs plugins with code execution may not be handled
4. **Limited error types**: Only handles a subset of mkdocs warning/error patterns

## Development Tasks

### Priority 1: Testing Infrastructure

Create test fixtures with known errors:

```
tests/
  fixtures/
    basic_site/           # Simple mkdocs site
      docs/
        index.md
      mkdocs.yml
    markdown_exec_error/  # Site with intentional code execution error
      docs/
        index.md          # Contains ```python exec="on" with raise ValueError
      mkdocs.yml
    multiple_errors/      # Site with various error types
    broken_links/         # Site with broken internal links
    missing_images/       # Site with missing image alt text
```

Each fixture should have:
- `mkdocs.yml` with appropriate plugins
- `docs/` directory with markdown files
- `expected_output.txt` with what the filter should produce
- `raw_mkdocs_output.txt` captured from actual mkdocs build

### Priority 2: Robustness Improvements

1. **Better file detection**: Parse mkdocs output more reliably to find which file caused errors
2. **Handle more error types**:
   - Broken internal links
   - Missing files referenced in nav
   - Plugin errors
   - Theme errors
   - YAML syntax errors in mkdocs.yml
3. **Handle streaming output** for `mkdocs serve` (currently waits for all input)
4. **Better deduplication**: Some warnings appear multiple times with slight variations

### Priority 3: New Features

1. **JSON output mode** for CI integration
2. **Config file support** for customizing which warnings to show/hide
3. **Watch mode** for continuous filtering during `mkdocs serve`

## Commands

```bash
# Install in development mode
uv sync

# Run the tool
echo "WARNING - test" | uv run mkdocs-filter

# Run linting
uv run ruff check .
uv run ruff format .

# Run tests (once created)
uv run pytest

# Build package
uv build

# Install pre-commit hooks
uv run pre-commit install
```

## Testing Strategy

1. **Unit tests** for parsing functions with raw input strings
2. **Integration tests** that build actual mkdocs fixtures and verify output
3. **Snapshot tests** comparing filter output against expected output files

Example test structure:

```python
def test_parses_markdown_exec_error():
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
        "INFO -  next log line",
    ]
    issues = parse_mkdocs_output(lines)
    assert len(issues) == 1
    assert issues[0].level == Level.WARNING
    assert issues[0].source == "markdown_exec"
    assert "ValueError: test" in issues[0].message
```

## Dependencies

- `rich>=13.0.0` - Terminal formatting
- Python 3.11+

Dev dependencies (add to pyproject.toml):
- `pytest` - Testing
- `ruff` - Linting and formatting

## File Structure

```
mkdocs-filter/
├── src/
│   └── mkdocs_filter/
│       └── __init__.py      # Main module
├── tests/
│   ├── fixtures/            # mkdocs test sites
│   │   ├── basic_site/
│   │   ├── markdown_exec_error/
│   │   └── ...
│   ├── test_parsing.py      # Unit tests for parsing
│   └── test_integration.py  # Integration tests
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── .pre-commit-config.yaml
└── CLAUDE.md
```

## Working with mkdocs Output

mkdocs output format varies by log level and plugin. Common patterns:

```
# Standard mkdocs warning
WARNING -  message here

# With timestamp (verbose mode)
2024-01-01 12:00:00,000 - mkdocs.xxx - WARNING - message

# markdown_exec with code block
WARNING -  markdown_exec: Execution of python code block exited with errors

Code block is:

  <indented code>

Output is:

  <indented traceback>

# Plugin-specific
WARNING -  [plugin-name] message

# Git revision plugin
WARNING -  [git-revision-date-localized-plugin] 'file.md' has no git logs
```

## Notes for Development

- Always test with real mkdocs output, not just unit tests
- The spinner uses Rich's Live display which can interfere with output - `transient=True` helps
- When parsing, be careful about line boundaries - some messages span multiple lines
- Use `--no-progress` flag when debugging to see cleaner output
