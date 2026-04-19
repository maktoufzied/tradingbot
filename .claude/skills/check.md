---
name: check
description: Run all code quality checks (lint, typecheck, test)
user_invocable: true
---

Run the full code quality suite:

```bash
task check
```

This runs:
1. `ruff check` - Linting (E, W, F, I, B, C4, UP, SIM rules)
2. `mypy --strict` - Type checking (Python 3.14)
3. `pytest` - Tests

Report any failures with file paths and line numbers.
