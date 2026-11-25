"""Tests for mypy and pyright configuration parsers."""

from pathlib import Path

from ty_migrate.parsers import discover_configs, parse_mypy_ini, parse_pyproject, parse_pyright_json, strip_jsonc


def test_strip_jsonc_preserves_urls_in_strings() -> None:
    raw = """
    {
      // top comment
      "url": "https://example.com/a//b/*c*/", /* inline block */
      "include": ["src",],
    }
    """
    cleaned = strip_jsonc(raw)
    assert '"https://example.com/a//b/*c*/"' in cleaned
    assert "top comment" not in cleaned
    assert "inline block" not in cleaned


def test_parse_mypy_ini_and_overrides(tmp_path: Path) -> None:
    ini = tmp_path / "mypy.ini"
    ini.write_text(
        """
[mypy]
python_version = 3.12
ignore_missing_imports = True
disable_error_code = attr-defined, arg-type
exclude = (^build/|^dist/)

[mypy-tests.*]
disable_error_code = return-value

[mypy-untyped_vendor.*]
ignore_missing_imports = True
""",
        encoding="utf-8",
    )
    cfg = parse_mypy_ini(ini)
    assert cfg.tool == "mypy"
    assert cfg.global_settings["python_version"] == "3.12"
    assert cfg.global_settings["ignore_missing_imports"] is True
    assert cfg.global_settings["disable_error_code"] == ["attr-defined", "arg-type"]
    assert len(cfg.overrides) == 2
    assert cfg.overrides[0].targets == ["tests.*"]


def test_parse_pyright_jsonc_and_execution_envs(tmp_path: Path) -> None:
    p = tmp_path / "pyrightconfig.json"
    p.write_text(
        """
        {
          // target python
          "pythonVersion": "3.13",
          "pythonPlatform": "Linux",
          "include": ["src"],
          "exclude": ["**/node_modules", "**/__pycache__"],
          "reportAttributeAccessIssue": "none",
          "reportDeprecated": "warning",
          "executionEnvironments": [
            {
              "root": "tests",
              "reportArgumentType": false,
            }
          ],
        }
        """,
        encoding="utf-8",
    )
    cfg = parse_pyright_json(p)
    assert cfg.tool == "pyright"
    assert cfg.global_settings["pythonVersion"] == "3.13"
    assert cfg.global_settings["reportAttributeAccessIssue"] == "none"
    assert len(cfg.overrides) == 1
    assert cfg.overrides[0].targets == ["tests"]
    assert cfg.overrides[0].settings["reportArgumentType"] is False


def test_parse_pyproject_mypy_and_basedpyright(tmp_path: Path) -> None:
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        """
[project]
name = "demo"
version = "0.1.0"

[tool.mypy]
python_version = "3.11"
warn_redundant_casts = true

[[tool.mypy.overrides]]
module = ["legacy.*"]
ignore_missing_imports = true

[tool.basedpyright]
pythonVersion = "3.11"
reportUnusedCoroutine = "error"
""",
        encoding="utf-8",
    )
    cfgs = discover_configs(tmp_path)
    tools = {c.tool for c in cfgs}
    assert tools == {"mypy", "basedpyright"}
    parsed = parse_pyproject(pp)
    assert len(parsed) == 2
