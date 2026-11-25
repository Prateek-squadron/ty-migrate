"""Parsers for mypy and pyright/basedpyright configuration files."""

from __future__ import annotations

import configparser
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SourceOverride:
    """Per-module or per-path override block from mypy or pyright."""

    targets: list[str]
    settings: dict[str, Any]
    source_label: str = ""


@dataclass
class SourceConfig:
    """Normalized configuration parsed from mypy and/or pyright."""

    tool: str  # "mypy", "pyright", or "basedpyright"
    origin: Path
    global_settings: dict[str, Any] = field(default_factory=dict)
    overrides: list[SourceOverride] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def strip_jsonc(text: str) -> str:
    """Strip // line comments, /* block comments */, and trailing commas from JSONC."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False

    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                if text[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
        else:
            out.append(ch)
            i += 1

    # Remove trailing commas before } or ] outside strings
    cleaned = "".join(out)
    final: list[str] = []
    in_string = False
    escape = False
    m = len(cleaned)
    j = 0
    while j < m:
        ch = cleaned[j]
        if in_string:
            final.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            j += 1
            continue

        if ch == '"':
            in_string = True
            final.append(ch)
            j += 1
        elif ch == ",":
            k = j + 1
            while k < m and cleaned[k] in " \t\r\n":
                k += 1
            if k < m and cleaned[k] in "}]":
                j += 1
                continue
            final.append(ch)
            j += 1
        else:
            final.append(ch)
            j += 1

    return "".join(final)


def _parse_ini_value(raw: str, key: str) -> Any:
    """Coerce mypy INI string values into Python primitives/lists."""
    text = raw.strip()
    lower = text.lower()
    if lower in {"true", "yes", "on"}:
        return True
    if lower in {"false", "no", "off"}:
        return False

    list_keys = {
        "files",
        "exclude",
        "mypy_path",
        "plugins",
        "enable_error_code",
        "disable_error_code",
        "always_true",
        "always_false",
        "disable_memoryview_promotion",
        "packages",
        "modules",
    }
    if key in list_keys or "\n" in text:
        items: list[str] = []
        for chunk in text.replace("\n", ",").split(","):
            item = chunk.strip()
            if item:
                items.append(item)
        return items

    return text


def parse_mypy_ini(path: Path) -> SourceConfig:
    """Parse mypy.ini, .mypy.ini, or setup.cfg."""
    parser = configparser.ConfigParser(interpolation=None)
    # Preserve case for keys just in case, though mypy keys are lowercase
    parser.optionxform = lambda optionstr: optionstr
    content = path.read_text(encoding="utf-8")
    parser.read_string(content, source=str(path))

    global_settings: dict[str, Any] = {}
    overrides: list[SourceOverride] = []
    warnings: list[str] = []

    if parser.has_section("mypy"):
        for k, v in parser.items("mypy"):
            key = k.strip().lower()
            global_settings[key] = _parse_ini_value(v, key)

    for section in parser.sections():
        if section == "mypy" or not section.startswith("mypy-"):
            continue
        mod_spec = section[len("mypy-") :].strip()
        targets = [m.strip() for m in mod_spec.split(",") if m.strip()]
        settings = {
            k.strip().lower(): _parse_ini_value(v, k.strip().lower())
            for k, v in parser.items(section)
        }
        overrides.append(
            SourceOverride(
                targets=targets,
                settings=settings,
                source_label=f"[{section}]",
            )
        )

    if not global_settings and not overrides:
        warnings.append(f"No [mypy] or [mypy-*] sections found in {path.name}.")

    return SourceConfig(
        tool="mypy",
        origin=path,
        global_settings=global_settings,
        overrides=overrides,
        warnings=warnings,
    )


def parse_pyright_json(path: Path) -> SourceConfig:
    """Parse pyrightconfig.json (supporting JSONC comments & trailing commas)."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(strip_jsonc(raw))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object at top level")

    return _build_pyright_source(data, origin=path, tool="pyright")


def _build_pyright_source(
    data: dict[str, Any], *, origin: Path, tool: str
) -> SourceConfig:
    global_settings: dict[str, Any] = {}
    overrides: list[SourceOverride] = []
    warnings: list[str] = []

    for k, v in data.items():
        if k == "executionEnvironments":
            if isinstance(v, list):
                for idx, env in enumerate(v):
                    if not isinstance(env, dict):
                        continue
                    root = env.get("root")
                    if not root:
                        warnings.append(
                            f"executionEnvironments[{idx}] is missing 'root' and was skipped."
                        )
                        continue
                    env_settings = {ek: ev for ek, ev in env.items() if ek != "root"}
                    overrides.append(
                        SourceOverride(
                            targets=[str(root)],
                            settings=env_settings,
                            source_label=f"executionEnvironments[{idx}] ({root})",
                        )
                    )
            continue
        global_settings[k] = v

    return SourceConfig(
        tool=tool,
        origin=origin,
        global_settings=global_settings,
        overrides=overrides,
        warnings=warnings,
    )


def parse_pyproject(path: Path) -> list[SourceConfig]:
    """Extract [tool.mypy], [tool.pyright], and [tool.basedpyright] from pyproject.toml."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    tool_tbl = data.get("tool", {})
    if not isinstance(tool_tbl, dict):
        return []

    configs: list[SourceConfig] = []

    mypy_tbl = tool_tbl.get("mypy")
    if isinstance(mypy_tbl, dict):
        global_settings: dict[str, Any] = {}
        overrides: list[SourceOverride] = []
        for k, v in mypy_tbl.items():
            if k == "overrides" and isinstance(v, list):
                for idx, ov in enumerate(v):
                    if not isinstance(ov, dict):
                        continue
                    mod = ov.get("module")
                    if isinstance(mod, str):
                        targets = [mod]
                    elif isinstance(mod, list):
                        targets = [str(m) for m in mod]
                    else:
                        targets = []
                    ov_settings = {ok: ov_val for ok, ov_val in ov.items() if ok != "module"}
                    overrides.append(
                        SourceOverride(
                            targets=targets,
                            settings=ov_settings,
                            source_label=f"[[tool.mypy.overrides]][{idx}]",
                        )
                    )
                continue
            global_settings[k] = v
        configs.append(
            SourceConfig(
                tool="mypy",
                origin=path,
                global_settings=global_settings,
                overrides=overrides,
            )
        )

    for key, tool_name in (("pyright", "pyright"), ("basedpyright", "basedpyright")):
        pyright_tbl = tool_tbl.get(key)
        if isinstance(pyright_tbl, dict):
            configs.append(_build_pyright_source(pyright_tbl, origin=path, tool=tool_name))

    return configs


def discover_configs(
    root: Path,
    *,
    source_filter: str = "auto",
    mypy_path: Path | None = None,
    pyright_path: Path | None = None,
    pyproject_path: Path | None = None,
) -> list[SourceConfig]:
    """Discover and parse mypy and/or pyright configs under root."""
    configs: list[SourceConfig] = []
    want_mypy = source_filter in {"auto", "mypy"}
    want_pyright = source_filter in {"auto", "pyright", "basedpyright"}

    if mypy_path is not None:
        if mypy_path.name == "pyproject.toml":
            configs.extend(c for c in parse_pyproject(mypy_path) if c.tool == "mypy")
        else:
            configs.append(parse_mypy_ini(mypy_path))

    if pyright_path is not None:
        if pyright_path.name == "pyproject.toml":
            configs.extend(
                c for c in parse_pyproject(pyright_path) if c.tool in {"pyright", "basedpyright"}
            )
        else:
            configs.append(parse_pyright_json(pyright_path))

    if pyproject_path is not None and pyproject_path not in {mypy_path, pyright_path}:
        for cfg in parse_pyproject(pyproject_path):
            if (cfg.tool == "mypy" and want_mypy) or (
                cfg.tool in {"pyright", "basedpyright"} and want_pyright
            ):
                configs.append(cfg)

    if mypy_path is not None or pyright_path is not None or pyproject_path is not None:
        return configs

    # Auto-discovery order matches official precedence
    if want_mypy:
        for candidate in ("mypy.ini", ".mypy.ini"):
            p = root / candidate
            if p.is_file():
                configs.append(parse_mypy_ini(p))
                break

    if want_pyright:
        p = root / "pyrightconfig.json"
        if p.is_file():
            configs.append(parse_pyright_json(p))

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        for cfg in parse_pyproject(pyproject):
            if cfg.tool == "mypy" and want_mypy and not any(c.tool == "mypy" for c in configs):
                configs.append(cfg)
            elif (
                cfg.tool in {"pyright", "basedpyright"}
                and want_pyright
                and not any(c.tool in {"pyright", "basedpyright"} for c in configs)
            ):
                configs.append(cfg)

    if want_mypy and not any(c.tool == "mypy" for c in configs):
        setup_cfg = root / "setup.cfg"
        if setup_cfg.is_file():
            parsed = parse_mypy_ini(setup_cfg)
            if parsed.global_settings or parsed.overrides:
                configs.append(parsed)

    return configs
