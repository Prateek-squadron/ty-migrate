# ty-migrate

**Automated migration CLI for moving Python projects from `mypy`, `pyright`, and `basedpyright` to Astral's `ty`.**

While `migrate-to-uv` handles Poetry/Pipenv to `uv` and Ruff replaces Flake8/Black/isort, Astral's `ty` has had no automated configuration or inline-suppression migrator—forcing teams to manually rewrite `mypy.ini`, `pyrightconfig.json`, `pyproject.toml`, and hundreds of `# type: ignore[...]` / `# pyright: ignore[...]` comments.

`ty-migrate` automates the migration with zero third-party dependencies (Python 3.11+ stdlib only):

- **Multi-format config discovery & parsing**:
  - `mypy.ini`, `.mypy.ini`, `setup.cfg` (`[mypy]` and `[mypy-*]`), `pyproject.toml` (`[tool.mypy]` + `[[tool.mypy.overrides]]`)
  - `pyrightconfig.json` (JSONC-aware: strips `//`, `/* */`, and trailing commas safely), `pyproject.toml` (`[tool.pyright]`, `[tool.basedpyright]`, and `executionEnvironments`)
- **Idiomatic `ty` TOML generation**:
  - Writes standalone `ty.toml` or safely inserts/updates `[tool.ty.*]` inside your existing `pyproject.toml` without disturbing other sections or comments.
  - Converts pure `ignore_missing_imports = true` module overrides into `[tool.ty.analysis].allowed-unresolved-imports`.
- **Tokenizer-safe inline suppression rewriting (`--rewrite-ignores`)**:
  - Uses Python's `tokenize` module so strings and docstrings containing `# type: ignore` are never touched.
  - Translates `# type: ignore[code]` and `# pyright: ignore[reportXyz]` into `# ty: ignore[ty-rule]` while preserving trailing comments.
- **Audit & CI modes**:
  - `--report` prints translated settings, implicit/default-strict guidance, and unmapped items.
  - `--diff` / `--dry-run` previews every change safely.
  - `--check` exits with code `3` if any settings or inline ignore codes remain unmapped.
  - `--verify` runs `ty check` after migration when `ty` is installed.

## Quick Start

```bash
# Preview migration and audit report
ty-migrate --dir . --dry-run --diff --report

# Write [tool.ty.*] to pyproject.toml (or ty.toml) and rewrite inline ignores
ty-migrate --dir . --rewrite-ignores --report

# Run via uvx without installing globally (once published)
uvx ty-migrate --dir . --rewrite-ignores --verify
```

## Example

Before (`mypy.ini` + Python code):

```ini
[mypy]
python_version = 3.12
ignore_missing_imports = True
warn_redundant_casts = True
disable_error_code = attr-defined

[mypy-tests.*]
disable_error_code = arg-type
```

```python
x: int = "bad"  # type: ignore[assignment]  # legacy fixture
```

After (`ty-migrate --target pyproject --rewrite-ignores`):

```toml
[tool.ty.environment]
python-version = "3.12"

[tool.ty.rules]
import-not-found = "ignore"
redundant-cast = "warn"
missing-attribute = "ignore"

[[tool.ty.overrides]]
include = ["tests/**"]
rules = { invalid-argument-type = "ignore" }
```

```python
x: int = "bad"  # ty: ignore[invalid-assignment]  # legacy fixture
```
