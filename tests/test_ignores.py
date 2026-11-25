"""Tests for tokenizer-safe inline ignore comment rewriting."""

from pathlib import Path

from ty_migrate.ignores import rewrite_python_source


def test_rewrite_mypy_and_pyright_ignores_safely() -> None:
    src = '''"""Docstring mentioning # type: ignore[arg-type] should not change."""
EXAMPLE = "# pyright: ignore[reportAttributeAccessIssue]"

x: int = "bad"  # type: ignore[assignment]  # keep reason
y = obj.missing  # pyright: ignore[reportAttributeAccessIssue]
z = fn(1, 2)  # type: ignore[arg-type, return-value]
bare = 1 + "a"  # type: ignore
unknown = 1  # type: ignore[custom-plugin-code]
'''
    res = rewrite_python_source(src, Path("sample.py"))
    assert '"""Docstring mentioning # type: ignore[arg-type] should not change."""' in res.new_text
    assert 'EXAMPLE = "# pyright: ignore[reportAttributeAccessIssue]"' in res.new_text
    assert "x: int = \"bad\"  # ty: ignore[invalid-assignment]  # keep reason" in res.new_text
    assert "y = obj.missing  # ty: ignore[missing-attribute, invalid-attribute-access]" in res.new_text
    assert "z = fn(1, 2)  # ty: ignore[invalid-argument-type, invalid-explicit-return]" in res.new_text
    # bare and unmapped stay untouched under defaults
    assert 'bare = 1 + "a"  # type: ignore' in res.new_text
    assert "unknown = 1  # type: ignore[custom-plugin-code]" in res.new_text
    assert res.rewritten_count == 3
    assert res.unmapped_codes == {"custom-plugin-code": 1}


def test_rewrite_bare_ignores_when_enabled() -> None:
    src = "a = 1 + 'x'  # type: ignore  # temporary\n"
    res = rewrite_python_source(src, Path("bare.py"), rewrite_bare=True)
    assert res.new_text == "a = 1 + 'x'  # ty: ignore  # temporary\n"
    assert res.rewritten_count == 1
