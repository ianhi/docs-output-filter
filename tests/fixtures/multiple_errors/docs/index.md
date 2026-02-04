# Page with Multiple Errors

This page demonstrates multiple error types.

## Code Execution Error

```python exec="on" session="errors"
import sys
print(f"Python version: {sys.version}")
raise RuntimeError("Intentional runtime error")
```

## Another Code Block

```python exec="on" session="errors2"
x = undefined_variable  # NameError
```

## Broken Link

See [this page](broken_link.md) for more info.

## Image without alt text

![](missing_image.png)
