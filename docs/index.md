# mkdocs-output-filter

**Filter mkdocs output to show only what matters: warnings and errors.**

Includes an [MCP server](mcp-server.md) for AI code assistant integration (Claude Code, etc.).

## What It Does

mkdocs-output-filter processes mkdocs build output and:

- **Shows** WARNING and ERROR level messages with rich formatting
- **Highlights** code execution errors (markdown_exec) with syntax-highlighted code blocks
- **Extracts** file locations, session names, and line numbers
- **Hides** routine INFO messages (building, cleaning, copying assets)

## Before & After

<div class="comparison">
<div class="comparison-item">
<div class="comparison-header bad">Raw mkdocs output</div>

```
INFO    -  Building documentation...
INFO    -  Cleaning site directory
INFO    -  Log level set to INFO
INFO    -  Building documentation to directory: /project/site
INFO    -  MERMAID2  - Initialization arguments: {}
INFO    -  Generating index pages...
INFO    -  Reading page 'index.md'
INFO    -  Reading page 'guide/getting-started.md'
INFO    -  Reading page 'guide/configuration.md'
INFO    -  Reading page 'api/reference.md'
INFO    -  Reading page 'api/models.md'
INFO    -  Copying static files from theme: material
INFO    -  Copying 'assets/stylesheets/extra.css'
INFO    -  Copying 'assets/javascripts/extra.js'
[git-revision-date-localized-plugin] 'docs/new-page.md' has no git logs
[git-revision-date-localized-plugin] 'docs/draft.md' has no git logs
[git-revision-date-localized-plugin] 'docs/changelog.md' has no git logs
INFO    -  Executing code blocks with markdown_exec...
WARNING -  markdown_exec: Execution of python code block exited with errors

Code block is:

  import numpy as np
  data = np.random.rand(10, 10)
  raise ValueError("INTENTIONAL TEST ERROR")

Output is:

  Traceback (most recent call last):
    File "<code block: session test; n1>", line 3, in <module>
      raise ValueError("INTENTIONAL TEST ERROR")
  ValueError: INTENTIONAL TEST ERROR

WARNING -  [git-revision-date-localized-plugin] Unable to read git logs
INFO    -  Rendering 'index.md'
INFO    -  Rendering 'guide/getting-started.md'
INFO    -  Rendering 'guide/configuration.md'
INFO    -  Rendering 'api/reference.md'
INFO    -  Rendering 'api/models.md'
INFO    -  Building search index...
INFO    -  Writing 'sitemap.xml'
INFO    -  Writing 'search/search_index.json'
INFO    -  Documentation built in 12.34 seconds
```

</div>
<div class="comparison-item">
<div class="comparison-header good">Filtered output</div>

<div class="terminal">
<span class="yellow">⚠ WARNING</span> <span class="dim">[markdown_exec]</span> ValueError: INTENTIONAL TEST ERROR
<span class="cyan">   📍 session </span><span class="green">'test'</span><span class="cyan"> → line </span><span class="cyan-bold">3</span>

<span class="cyan">╭─────────────────── Code Block ───────────────────╮</span>
<span class="cyan">│</span><span class="code-bg">   <span class="line-num">1</span> <span class="keyword">import</span> numpy <span class="keyword">as</span> np                          </span><span class="cyan">│</span>
<span class="cyan">│</span><span class="code-bg">   <span class="line-num">2</span> data = np.random.rand(<span class="number">10</span>, <span class="number">10</span>)                </span><span class="cyan">│</span>
<span class="cyan">│</span><span class="code-bg">   <span class="line-num">3</span> <span class="keyword">raise</span> <span class="exception">ValueError</span>(<span class="string">"INTENTIONAL TEST ERROR"</span>)  </span><span class="cyan">│</span>
<span class="cyan">╰──────────────────────────────────────────────────╯</span>
<span class="red">╭────────────── Error Output ──────────────╮</span>
<span class="red">│</span> ValueError: INTENTIONAL TEST ERROR       <span class="red">│</span>
<span class="red">╰────────── use -v for full traceback ─────╯</span>

<span class="yellow">⚠ WARNING</span> <span class="dim">[git-revision]</span> Unable to read git logs

<span class="dim">────────────────────────────────────────</span>
Summary: <span class="yellow">2 warning(s)</span>

<span class="green-bold">🌐 Server:</span> http://127.0.0.1:8000/
<span class="blue-bold">📁 Output:</span> /project/site
<span class="dim">Built in </span><span class="cyan">12.34</span><span class="dim">s</span>
</div>

</div>
</div>

## Install

```bash
# With uv (recommended)
uv tool install mkdocs-output-filter

# With pip
pip install mkdocs-output-filter
```

## Quick Start

```bash
# Filter build output
mkdocs build 2>&1 | mkdocs-output-filter

# Filter serve output (stays running, updates on file changes)
mkdocs serve --livereload 2>&1 | mkdocs-output-filter

# With AI assistant integration (writes state for MCP server)
mkdocs serve --livereload 2>&1 | mkdocs-output-filter --share-state
```

## Features

| Feature | Description |
|---------|-------------|
| **Filtered output** | Shows WARNING and ERROR messages, hides routine INFO |
| **Code blocks** | Syntax-highlighted code that caused markdown_exec errors |
| **Location info** | File, session name, and line number extraction |
| **Streaming mode** | Real-time output for `mkdocs serve` with rebuild detection |
| **Interactive mode** | Toggle between raw/filtered with keyboard (`-i`) |
| **MCP server** | API for AI code assistants like Claude Code |

## Options

| Flag | Description |
|------|-------------|
| `-v, --verbose` | Show full tracebacks and code blocks |
| `-e, --errors-only` | Hide warnings, show only errors |
| `--no-color` | Disable colored output |
| `--raw` | Pass through unfiltered mkdocs output |
| `-i, --interactive` | Toggle raw/filtered with keyboard |
| `--share-state` | Write state for MCP server integration |

See [Usage](usage.md) for more details and [MCP Server](mcp-server.md) for AI assistant integration.
