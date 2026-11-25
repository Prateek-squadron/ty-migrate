# ty-migrate

<p align="center">
  <strong>Automated migration CLI for moving Python projects from <code>mypy</code>, <code>pyright</code>, and <code>basedpyright</code> to Astral's <code>ty</code></strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/ty-migrate/"><img src="https://img.shields.io/pypi/v/ty-migrate.svg?color=blue" alt="PyPI version"></a>
  <a href="https://github.com/Prateek-squadron/ty-migrate/actions/workflows/ci.yml"><img src="https://github.com/Prateek-squadron/ty-migrate/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://github.com/Prateek-squadron/ty-migrate/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen.svg" alt="Zero Dependencies">
</p>

---

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
# Run directly with uvx (zero install)
uvx ty-migrate --rewrite-ignores --report --verify

# Or preview changes safely first
uvx ty-migrate --dir . --rewrite-ignores --dry-run --diff --report

# Or install globally / with pip
pip install ty-migrate
```

## Example Output

```console
$ ty-migrate --rewrite-ignores --dry-run --diff --report
--- a/ty.toml
+++ b/ty.toml
@@ -0,0 +1,14 @@
+[environment]
+python-version = "3.12"
+
+[analysis]
+allowed-unresolved-imports = ["vendor_missing.*"]
+
+[rules]
+import-not-found = "ignore"
+redundant-cast = "warn"
+missing-attribute = "ignore"
+
+[[overrides]]
+include = ["tests/**"]
+rules = { invalid-argument-type = "ignore" }

--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-x: int = "bad"  # type: ignore[assignment]  # legacy fixture
+x: int = "bad"  # ty: ignore[invalid-assignment]  # legacy fixture
=== ty-migrate Audit Report ===
Sources: mypy (mypy.ini)
Summary: 6 translated, 1 guidance/implicit, 0 unmapped

[Translated]
  - mypy.ini:python_version -> environment.python-version (3.12)
  - mypy.ini:ignore_missing_imports=True -> rules.import-not-found=ignore
  - mypy.ini:warn_redundant_casts=True -> rules.redundant-cast=warn
  - mypy.ini:error_code:attr-defined -> rules.missing-attribute=ignore
  - mypy.ini:[mypy-vendor_missing.*] -> analysis.allowed-unresolved-imports (vendor_missing.*)
  - mypy.ini:[mypy-tests.*]:error_code:arg-type -> rules.invalid-argument-type=ignore

[Guidance / Implicit in ty]
  - mypy.ini:strict=True -> (implicit / guidance) (ty has no single `strict` flag (its defaults are already strict); enable extra strict rules like `possibly-missing-attribute` or `unsound-return` in `[tool.ty.rules]` if desired.)

[Inline Ignore Comments]
  - Rewritten: 1
  - Unchanged: 0
```
