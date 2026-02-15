# Quality gate (Python)

After any code changes:
- ruff check .

Before marking the task as done:
- pyright

Before commit/push:
- pytest

Type correctness is validated via:
- Python LSP (Pylance / Pyright in editor, interactive)
- `pyright` (CLI, strict mode)

Linting is handled by:
- Ruff

Formatting is handled by:
- Black

Ruff is NOT used as a type checker.
Black is NOT used for linting.
LSP is NOT a replacement for CLI typecheck.

