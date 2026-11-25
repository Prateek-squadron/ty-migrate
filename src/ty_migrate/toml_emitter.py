"""TOML rendering for ty.toml and pyproject.toml [tool.ty.*] sections."""

from __future__ import annotations

import re
from typing import Any

from ty_migrate.migrator import TyConfig


def _toml_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_val(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _toml_str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        if len(value) == 1 and len(str(value[0])) < 50:
            return f"[{_toml_val(value[0])}]"
        inner = ",\n".join(f"    {_toml_val(item)}" for item in value)
        return f"[\n{inner},\n]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{_toml_key(k)} = {_toml_val(v)}" for k, v in value.items())
        return f"{{ {pairs} }}"
    return _toml_str(str(value))


def _toml_key(key: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return _toml_str(key)


def render_ty_toml(cfg: TyConfig, *, pyproject_prefix: bool = False) -> str:
    """Render a TyConfig to clean TOML (either standalone ty.toml or [tool.ty.*])."""
    prefix = "tool.ty." if pyproject_prefix else ""
    sections: list[str] = []

    def emit_table(name: str, data: dict[str, Any]) -> None:
        if not data:
            return
        lines = [f"[{prefix}{name}]"]
        for k, v in data.items():
            lines.append(f"{_toml_key(k)} = {_toml_val(v)}")
        sections.append("\n".join(lines))

    emit_table("environment", cfg.environment)
    emit_table("src", cfg.src)
    emit_table("analysis", cfg.analysis)
    emit_table("rules", cfg.rules)
    emit_table("terminal", cfg.terminal)

    for ov in cfg.overrides:
        lines = [f"[[{prefix}overrides]]"]
        if ov.include:
            lines.append(f"include = {_toml_val(ov.include)}")
        if ov.exclude:
            lines.append(f"exclude = {_toml_val(ov.exclude)}")
        if ov.rules:
            lines.append(f"rules = {_toml_val(ov.rules)}")
        sections.append("\n".join(lines))

    if not sections:
        # Always emit a valid marker table if nothing needed overriding
        header = "[tool.ty]" if pyproject_prefix else "# Default ty configuration (no overrides needed)"
        return header + "\n"

    return "\n\n".join(sections) + "\n"


_SECTION_HEADER_RE = re.compile(r"^\s*(\[\[?)\s*([^\[\]\n#]+?)\s*(\]\]?)\s*(?:#.*)?$")


def upsert_pyproject_toml(existing_text: str, ty_toml_block: str) -> str:
    """Insert or replace [tool.ty*] sections in an existing pyproject.toml safely."""
    lines = existing_text.splitlines(keepends=True)
    kept: list[str] = []
    skipping_ty_section = False

    for line in lines:
        m = _SECTION_HEADER_RE.match(line)
        if m:
            header_name = m.group(2).strip()
            is_ty = (
                header_name == "tool.ty"
                or header_name.startswith("tool.ty.")
            )
            skipping_ty_section = is_ty
            if is_ty:
                continue
        if not skipping_ty_section:
            kept.append(line)

    base = "".join(kept).rstrip()
    block = ty_toml_block.strip()
    if not base:
        return block + "\n"
    return f"{base}\n\n{block}\n"
