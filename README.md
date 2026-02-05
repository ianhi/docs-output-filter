# mkdocs-filter

Filter mkdocs build output to show only warnings and errors with nice formatting.

## Before & After

<table>
<tr>
<td><strong>Raw mkdocs output</strong></td>
<td><strong>Filtered output</strong></td>
</tr>
<tr>
<td>

```
INFO    -  Cleaning site directory
INFO    -  Building documentation...
WARNING -  markdown_exec: Execution of
python code block exited with errors

Code block is:

  raise ValueError("test error")

Output is:

  Traceback (most recent call last):
    File "<code block>", line 1
      raise ValueError("test error")
  ValueError: test error

INFO    -  Documentation built in 1.23s
```

</td>
<td>

```
⚠ WARNING [markdown_exec] ValueError: test error
   📍 session 'test' → line 1

╭──────────────── Code Block ────────────────╮
│   1 raise ValueError("test error")         │
╰────────────────────────────────────────────╯

Summary: 1 warning(s)
Built in 1.23s
```

</td>
</tr>
</table>

## Installation

```bash
uv tool install mkdocs-filter
```

## Usage

```bash
mkdocs build 2>&1 | mkdocs-output-filter
mkdocs serve --livereload 2>&1 | mkdocs-output-filter
```

> **Note:** Use `--livereload` with `mkdocs serve` due to a [Click 8.3.x bug](https://github.com/mkdocs/mkdocs/issues/4032).

## Options

| Flag | Description |
|------|-------------|
| `-v, --verbose` | Show full tracebacks |
| `-e, --errors-only` | Show only errors |
| `--no-color` | Disable colors |
| `--raw` | Pass through unfiltered |
| `-i, --interactive` | Toggle filtered/raw with keyboard |

## Development

```bash
git clone https://github.com/ianhi/mkdocs-filter
cd mkdocs-filter
uv sync
uv run pre-commit install
uv run pytest
```

## License

MIT
