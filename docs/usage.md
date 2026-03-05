# Usage

## Basic Usage

The recommended way to use docs-output-filter is **wrapper mode** — prefix your build command with `docs-output-filter --`:

```bash
# MkDocs
docs-output-filter -- mkdocs build
docs-output-filter -- mkdocs serve --livereload

# Sphinx / sphinx-autobuild
docs-output-filter -- sphinx-build docs _build
docs-output-filter -- sphinx-autobuild docs _build/html
```

!!! tip "Why wrapper mode?"
    Wrapper mode runs the command for you, automatically captures both stdout and stderr, and fixes Python buffering issues that can prevent sphinx-autobuild's server URL from appearing. No `2>&1` needed.

You can also use traditional **pipe mode**:

```bash
mkdocs build 2>&1 | docs-output-filter
sphinx-build docs _build 2>&1 | docs-output-filter
```

!!! note "Why `2>&1` in pipe mode?"
    Sphinx writes warnings and errors to **stderr**. Without `2>&1`, they bypass the filter
    entirely and print directly to your terminal. MkDocs writes everything to stdout, so
    `2>&1` is optional but harmless — we recommend always including it. Wrapper mode handles
    this automatically.

!!! warning "Click 8.3.x Bug"
    Due to a [bug in Click 8.3.x](https://github.com/mkdocs/mkdocs/issues/4032),
    you must use `--livereload` flag for file watching to work properly with
    `mkdocs serve`.

## Build Tool Detection

docs-output-filter auto-detects whether you're running MkDocs or Sphinx from the output. You can force a specific tool:

```bash
# Auto-detect (default)
docs-output-filter -- sphinx-build docs _build

# Force Sphinx
docs-output-filter --tool sphinx -- some-command

# Force MkDocs
docs-output-filter --tool mkdocs -- some-command
```

## Command-Line Options

| Flag | Description |
|------|-------------|
| `-- COMMAND` | Run command as subprocess (recommended, no `2>&1` needed) |
| `-v, --verbose` | Show full code blocks and tracebacks |
| `-e, --errors-only` | Show only errors, not warnings |
| `--no-color` | Disable colored output |
| `--no-progress` | Disable progress spinner |
| `--raw` | Pass through raw build output |
| `--streaming` | Force streaming mode (for `mkdocs serve` / `sphinx-autobuild`) |
| `--batch` | Force batch mode (process all input then display) |
| `-i, --interactive` | Interactive mode with keyboard controls |
| `--tool mkdocs\|sphinx\|auto` | Force build tool detection (default: auto) |
| `--share-state` | Write issues to state file for MCP server |
| `--json` | Machine-readable JSON output (for LLMs, scripts, CI) |
| `--url URL` | Fetch and process a remote build log (e.g., ReadTheDocs) |
| `--version` | Show version number |

## Modes

### Wrapper Mode (recommended)

Runs your build command as a subprocess, automatically capturing both stdout and stderr. Sets `PYTHONUNBUFFERED=1` to fix Python buffering issues (e.g., sphinx-autobuild's server URL not appearing in pipe mode).

```bash
docs-output-filter -- mkdocs build
docs-output-filter -- mkdocs serve --livereload
docs-output-filter -- sphinx-autobuild docs _build/html
```

Place docs-output-filter flags **before** the `--`:

```bash
docs-output-filter -v -- mkdocs build --verbose
docs-output-filter -e --no-color -- sphinx-build docs _build
```

The `--` is standard Unix convention meaning "end of options" — everything after it is the command to run.

### Batch Mode (default for one-shot builds)

Reads all build output, parses it, then displays a summary. Shows a progress spinner while processing. This is the default when piping one-shot build commands.

```bash
mkdocs build 2>&1 | docs-output-filter
sphinx-build docs _build 2>&1 | docs-output-filter
```

### Streaming Mode (default for serve/watch commands)

Processes output in real-time, detecting chunk boundaries like build completion and file changes. Shows issues as they occur. This is the default mode (use `--batch` to force batch mode).

```bash
docs-output-filter -- mkdocs serve --livereload
docs-output-filter -- sphinx-autobuild docs _build/html
```

Or with pipe mode:

```bash
mkdocs serve --livereload 2>&1 | docs-output-filter
sphinx-autobuild docs _build/html 2>&1 | docs-output-filter
```

When a file change triggers a rebuild, you'll see:

```
═══════════════════════════════════════════════
🔄 File change detected — rebuilding...
═══════════════════════════════════════════════
```

### Interactive Mode

Toggle between filtered and raw output using keyboard controls:

```bash
docs-output-filter -i -- mkdocs serve --livereload
```

**Keyboard controls:**

- `r` - Switch to raw mode (show all output)
- `f` - Switch to filtered mode (show only warnings/errors)
- `q` - Quit

!!! note
    Interactive mode requires a TTY. When piped or in non-interactive terminals, it falls back to streaming mode.

## Examples

### Verbose Output

Show full tracebacks for debugging:

```bash
docs-output-filter -v -- mkdocs build
docs-output-filter -v -- sphinx-build docs _build
```

### Errors Only

Hide warnings, show only errors:

```bash
docs-output-filter -e -- mkdocs build
```

### CI/CD Integration

For CI environments, disable colors and progress:

```bash
docs-output-filter --no-color --no-progress -- mkdocs build
docs-output-filter --no-color --no-progress -- sphinx-build docs _build
```

The exit code is:
- `0` - No errors (warnings are OK)
- `1` - One or more errors found

### Raw Passthrough

Sometimes you need the full build output:

```bash
docs-output-filter --raw -- mkdocs build
```

### Remote Build Logs

Fetch and process build logs from remote CI/CD systems like ReadTheDocs:

```bash
# ReadTheDocs - just paste the build URL from your browser
docs-output-filter --url https://app.readthedocs.org/projects/myproject/builds/12345/

# Any text log file
docs-output-filter --url https://example.com/build.log
```

This is useful for debugging failed builds on CI services without copying logs manually.

**Supported formats:**

- **ReadTheDocs** - paste the web UI URL directly, auto-transforms to raw log
- Plain text log files
- JSON with common log fields (`output`, `log`, `logs`, `build_log`, `stdout`, `stderr`)

### JSON Output

For machine-readable output (useful for LLMs, scripts, and CI pipelines), use `--json`:

```bash
# Pipe mode
mkdocs build 2>&1 | docs-output-filter --json

# With a remote build log
docs-output-filter --url https://app.readthedocs.org/projects/myproject/builds/12345/ --json

# Verbose (full tracebacks instead of condensed)
mkdocs build 2>&1 | docs-output-filter --json -v
```

Output is a JSON object with issues, info summary, and build info — ANSI codes are stripped and tracebacks are condensed by default:

```json
{
  "total": 1,
  "errors": 0,
  "warnings": 1,
  "issues": [
    {
      "level": "WARNING",
      "source": "markdown_exec",
      "message": "ValueError: test error",
      "file": "docs/index.md",
      "output": "ValueError: test error"
    }
  ],
  "build_info": {
    "build_dir": "site",
    "build_time": "1.23"
  }
}
```

### With AI Code Assistants

Enable state sharing so Claude Code (or other AI assistants) can access build issues:

```bash
docs-output-filter --share-state -- mkdocs serve --livereload
```

This writes a state file (in a temp directory) that the [MCP server](mcp-server.md) can read. No files are created in your project directory. See the [MCP Server docs](mcp-server.md) for setup instructions.
