"""Tests for config migration logic, rule catalog validation, and TOML emission."""

import tomllib
from pathlib import Path

from ty_migrate.mappings import (
    MYPY_BOOL_FLAG_TO_TY_RULE,
    MYPY_ERROR_CODE_TO_TY_RULES,
    PYRIGHT_REPORT_TO_TY_RULES,
    validate_rule_catalog,
)
from ty_migrate.migrator import migrate_configs
from ty_migrate.parsers import discover_configs
from ty_migrate.toml_emitter import render_ty_toml, upsert_pyproject_toml
from ty_migrate.ty_rules import TY_RULES


def test_all_mapped_rules_exist_in_ty_catalog() -> None:
    validate_rule_catalog()
    assert "missing-attribute" in TY_RULES
    assert "invalid-argument-type" in TY_RULES
    assert len(MYPY_ERROR_CODE_TO_TY_RULES) >= 40
    assert len(PYRIGHT_REPORT_TO_TY_RULES) >= 50
    assert len(MYPY_BOOL_FLAG_TO_TY_RULE) >= 5


def test_migrate_mypy_and_upsert_pyproject(tmp_path: Path) -> None:
    (tmp_path / "mypy.ini").write_text(
        """
[mypy]
python_version = 3.12
platform = linux2
mypy_path = stubs, extra_stubs
files = src, tests
exclude = (^build/|^dist/)
ignore_missing_imports = True
warn_redundant_casts = True
disable_error_code = attr-defined, union-attr
strict = True

[mypy-vendor_missing.*]
ignore_missing_imports = True

[mypy-tests.*]
disable_error_code = arg-type
""",
        encoding="utf-8",
    )
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """[project]
name = "sample"
version = "0.1.0"

[tool.ty.rules]
old-rule = "ignore"

[tool.ruff]
line-length = 100
""",
        encoding="utf-8",
    )

    configs = discover_configs(tmp_path)
    ty_cfg, report = migrate_configs(configs)

    assert ty_cfg.environment["python-version"] == "3.12"
    assert ty_cfg.environment["python-platform"] == "linux"
    assert ty_cfg.environment["extra-paths"] == ["stubs", "extra_stubs"]
    assert ty_cfg.src["include"] == ["src", "tests"]
    assert ty_cfg.src["exclude"] == ["build/", "dist/"]
    assert ty_cfg.analysis["allowed-unresolved-imports"] == ["vendor_missing.*"]
    assert ty_cfg.rules["import-not-found"] == "ignore"
    assert ty_cfg.rules["redundant-cast"] == "warn"
    assert ty_cfg.rules["missing-attribute"] == "ignore"
    assert ty_cfg.rules["missing-union-attribute"] == "ignore"
    assert len(ty_cfg.overrides) == 1
    assert ty_cfg.overrides[0].include == ["tests/**"]
    assert ty_cfg.overrides[0].rules == {"invalid-argument-type": "ignore"}
    assert report.unmapped_count == 0
    assert report.guidance_count >= 1  # strict = True guidance

    block = render_ty_toml(ty_cfg, pyproject_prefix=True)
    updated = upsert_pyproject_toml(pyproject.read_text(encoding="utf-8"), block)

    parsed = tomllib.loads(updated)
    assert "old-rule" not in parsed["tool"]["ty"]["rules"]
    assert parsed["tool"]["ruff"]["line-length"] == 100
    assert parsed["tool"]["ty"]["environment"]["python-version"] == "3.12"


def test_migrate_pyright_severities(tmp_path: Path) -> None:
    (tmp_path / "pyrightconfig.json").write_text(
        """
        {
          "pythonVersion": "3.13.1",
          "pythonPlatform": "Darwin",
          "reportAttributeAccessIssue": "none",
          "reportDeprecated": "information",
          "reportReturnType": "error",
          "typeCheckingMode": "strict"
        }
        """,
        encoding="utf-8",
    )
    configs = discover_configs(tmp_path)
    ty_cfg, report = migrate_configs(configs)
    assert ty_cfg.environment["python-version"] == "3.13"
    assert ty_cfg.environment["python-platform"] == "darwin"
    assert ty_cfg.rules["missing-attribute"] == "ignore"
    assert ty_cfg.rules["deprecated"] == "warn"
    assert ty_cfg.rules["invalid-explicit-return"] == "error"
    assert report.unmapped_count == 0
