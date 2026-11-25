"""End-to-end tests including CLI execution and live validation against Astral ty."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ty_migrate.cli import main


def test_cli_json_and_check_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "mypy.ini").write_text(
        "[mypy]\npython_version = 3.12\nunknown_legacy_flag = True\n",
        encoding="utf-8",
    )
    rc = main(["--dir", str(tmp_path), "--json", "--check", "--dry-run"])
    assert rc == 3
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["summary"]["unmapped"] == 1
    assert data["summary"]["translated"] == 1


def test_e2e_migrated_project_passes_real_ty_check(tmp_path: Path) -> None:
    """Create a realistic mypy+pyright project, migrate it, and validate with live ty binary."""
    (tmp_path / "stubs").mkdir()
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    (tmp_path / "pyproject.toml").write_text(
        """[project]
name = "e2e-demo"
version = "0.1.0"
requires-python = ">=3.12"
""",
        encoding="utf-8",
    )
    (tmp_path / "mypy.ini").write_text(
        """[mypy]
python_version = 3.12
mypy_path = stubs
disable_error_code = attr-defined

[mypy-vendor_missing.*]
ignore_missing_imports = True

[mypy-tests.*]
disable_error_code = assignment
""",
        encoding="utf-8",
    )
    (src_dir / "app.py").write_text(
        """import vendor_missing.client  # suppressed by allowed-unresolved-imports
import another_missing_pkg  # type: ignore[import-not-found]


class Box:
    value: int = 1


def broken(b: Box) -> int:
    _ = b.nonexistent  # suppressed globally by attr-defined -> missing-attribute = "ignore"
    x: int = "wrong"  # type: ignore[assignment]
    return 42
""",
        encoding="utf-8",
    )
    (tests_dir / "test_app.py").write_text(
        """def test_override() -> None:
    n: int = "allowed by tests/** override"
    assert n
""",
        encoding="utf-8",
    )

    rc = main(["--dir", str(tmp_path), "--rewrite-ignores", "--check"])
    assert rc == 0

    app_text = (src_dir / "app.py").read_text(encoding="utf-8")
    assert "# ty: ignore[invalid-assignment]" in app_text
    assert "# ty: ignore[import-not-found]" in app_text

    # Run the real ty binary (either `ty` on PATH or cached `uvx --offline ty==0.0.109`)
    ty_bin = shutil.which("ty")
    if ty_bin:
        cmd = [ty_bin, "check", "--project", str(tmp_path)]
    elif shutil.which("uvx"):
        cmd = ["uvx", "--offline", "ty==0.0.109", "check", "--project", str(tmp_path)]
    else:
        pytest.skip("ty binary not available locally")

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"ty check failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
