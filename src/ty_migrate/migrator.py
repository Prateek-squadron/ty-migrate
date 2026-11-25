"""Core migration engine translating mypy/pyright configs into Astral ty config + report."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ty_migrate.mappings import (
    MYPY_BOOL_FLAG_TO_TY_RULE,
    MYPY_ERROR_CODE_TO_TY_RULES,
    MYPY_UNSUPPORTED_OR_IMPLICIT,
    PYRIGHT_REPORT_TO_TY_RULES,
    PYRIGHT_UNSUPPORTED_OR_IMPLICIT,
    mypy_module_to_glob,
    mypy_regex_exclude_to_globs,
    normalize_platform,
    normalize_pyright_severity,
    normalize_python_version,
)
from ty_migrate.parsers import SourceConfig, SourceOverride


@dataclass
class TyOverride:
    """Represents a [[tool.ty.overrides]] entry."""

    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    rules: dict[str, str] = field(default_factory=dict)


@dataclass
class TyConfig:
    """Normalized Astral ty configuration model."""

    environment: dict[str, Any] = field(default_factory=dict)
    src: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    rules: dict[str, str] = field(default_factory=dict)
    terminal: dict[str, Any] = field(default_factory=dict)
    overrides: list[TyOverride] = field(default_factory=list)


@dataclass
class ReportItem:
    """Single migration audit entry."""

    source: str
    target: str
    status: str  # "translated", "guidance", "unmapped"
    detail: str = ""


@dataclass
class MigrationReport:
    """Structured audit report of everything translated, implicit, or unmapped."""

    sources: list[str] = field(default_factory=list)
    items: list[ReportItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ignores_rewritten: int = 0
    ignores_unchanged: int = 0
    unmapped_ignore_codes: dict[str, int] = field(default_factory=dict)
    files_modified: list[str] = field(default_factory=list)

    @property
    def translated_count(self) -> int:
        return sum(1 for i in self.items if i.status == "translated")

    @property
    def guidance_count(self) -> int:
        return sum(1 for i in self.items if i.status == "guidance")

    @property
    def unmapped_count(self) -> int:
        return sum(1 for i in self.items if i.status == "unmapped") + len(
            self.unmapped_ignore_codes
        )

    def has_issues(self) -> bool:
        return self.unmapped_count > 0


def _append_unique(target_list: list[str], items: list[str]) -> None:
    for item in items:
        if item not in target_list:
            target_list.append(item)


def _ensure_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    if isinstance(val, str):
        return [v.strip() for v in val.replace("\n", ",").split(",") if v.strip()]
    return []


def migrate_configs(configs: list[SourceConfig]) -> tuple[TyConfig, MigrationReport]:
    """Migrate a list of parsed mypy/pyright configs into a unified TyConfig + report."""
    ty_cfg = TyConfig()
    report = MigrationReport(sources=[f"{c.tool} ({c.origin})" for c in configs])

    for cfg in configs:
        report.warnings.extend(cfg.warnings)
        if cfg.tool == "mypy":
            _apply_mypy_config(cfg, ty_cfg, report)
        elif cfg.tool in {"pyright", "basedpyright"}:
            _apply_pyright_config(cfg, ty_cfg, report)

    return ty_cfg, report


def _apply_mypy_config(cfg: SourceConfig, ty_cfg: TyConfig, report: MigrationReport) -> None:
    src_label = cfg.origin.name
    for key, val in cfg.global_settings.items():
        if key == "python_version":
            ver = normalize_python_version(val)
            if ver:
                ty_cfg.environment["python-version"] = ver
                report.items.append(
                    ReportItem(f"{src_label}:python_version", "environment.python-version", "translated", ver)
                )
        elif key == "platform":
            plat = normalize_platform(val)
            if plat:
                ty_cfg.environment["python-platform"] = plat
                report.items.append(
                    ReportItem(f"{src_label}:platform", "environment.python-platform", "translated", plat)
                )
        elif key == "mypy_path":
            paths = _ensure_list(val)
            if paths:
                existing = ty_cfg.environment.setdefault("extra-paths", [])
                _append_unique(existing, paths)
                report.items.append(
                    ReportItem(f"{src_label}:mypy_path", "environment.extra-paths", "translated", ", ".join(paths))
                )
        elif key == "custom_typeshed_dir":
            ty_cfg.environment["typeshed"] = str(val)
            report.items.append(
                ReportItem(f"{src_label}:custom_typeshed_dir", "environment.typeshed", "translated", str(val))
            )
        elif key == "python_executable":
            ty_cfg.environment["python"] = str(val)
            report.items.append(
                ReportItem(f"{src_label}:python_executable", "environment.python", "translated", str(val))
            )
        elif key in {"files", "packages", "modules"}:
            items = _ensure_list(val)
            if key in {"packages", "modules"}:
                items = [m.replace(".", "/") for m in items]
            if items:
                existing = ty_cfg.src.setdefault("include", [])
                _append_unique(existing, items)
                report.items.append(
                    ReportItem(f"{src_label}:{key}", "src.include", "translated", ", ".join(items))
                )
        elif key == "exclude":
            globs, unmapped = mypy_regex_exclude_to_globs(val)
            if globs:
                existing = ty_cfg.src.setdefault("exclude", [])
                _append_unique(existing, globs)
                report.items.append(
                    ReportItem(f"{src_label}:exclude", "src.exclude", "translated", ", ".join(globs))
                )
            for pat in unmapped:
                report.items.append(
                    ReportItem(
                        f"{src_label}:exclude",
                        "src.exclude",
                        "unmapped",
                        f"Regex exclude pattern could not be cleanly converted to glob: {pat!r}",
                    )
                )
        elif key == "disable_error_code":
            for code in _ensure_list(val):
                _map_mypy_error_code(code, "ignore", src_label, ty_cfg.rules, report)
        elif key == "enable_error_code":
            for code in _ensure_list(val):
                _map_mypy_error_code(code, "error", src_label, ty_cfg.rules, report)
        elif key in MYPY_BOOL_FLAG_TO_TY_RULE:
            ty_rule, when_true, when_false = MYPY_BOOL_FLAG_TO_TY_RULE[key]
            sev = when_true if bool(val) else when_false
            ty_cfg.rules[ty_rule] = sev
            report.items.append(
                ReportItem(f"{src_label}:{key}={val}", f"rules.{ty_rule}={sev}", "translated")
            )
        elif key == "pretty":
            ty_cfg.terminal["output-format"] = "full" if bool(val) else "concise"
            report.items.append(
                ReportItem(
                    f"{src_label}:pretty={val}",
                    f"terminal.output-format={ty_cfg.terminal['output-format']}",
                    "translated",
                )
            )
        elif key in MYPY_UNSUPPORTED_OR_IMPLICIT:
            report.items.append(
                ReportItem(
                    f"{src_label}:{key}={val}",
                    "(implicit / guidance)",
                    "guidance",
                    MYPY_UNSUPPORTED_OR_IMPLICIT[key],
                )
            )
        else:
            report.items.append(
                ReportItem(
                    f"{src_label}:{key}={val}",
                    "(unmapped)",
                    "unmapped",
                    f"No direct ty equivalent for mypy setting {key!r}",
                )
            )

    for ov in cfg.overrides:
        _apply_mypy_override(ov, src_label, ty_cfg, report)


def _map_mypy_error_code(
    code: str,
    severity: str,
    src_label: str,
    rules_dict: dict[str, str],
    report: MigrationReport,
) -> None:
    targets = MYPY_ERROR_CODE_TO_TY_RULES.get(code)
    if targets:
        for rule in targets:
            rules_dict[rule] = severity
        report.items.append(
            ReportItem(
                f"{src_label}:error_code:{code}",
                ", ".join(f"rules.{r}={severity}" for r in targets),
                "translated",
            )
        )
    else:
        report.items.append(
            ReportItem(
                f"{src_label}:error_code:{code}",
                "(unmapped)",
                "unmapped",
                f"No direct ty rule mapping for mypy error code {code!r}",
            )
        )


def _apply_mypy_override(
    ov: SourceOverride,
    src_label: str,
    ty_cfg: TyConfig,
    report: MigrationReport,
) -> None:
    # Special-case pure ignore_missing_imports = true -> analysis.allowed-unresolved-imports
    if (
        set(ov.settings.keys()) <= {"ignore_missing_imports", "follow_imports"}
        and ov.settings.get("ignore_missing_imports") is True
        and ov.targets
    ):
        allowed = ty_cfg.analysis.setdefault("allowed-unresolved-imports", [])
        _append_unique(allowed, ov.targets)
        report.items.append(
            ReportItem(
                f"{src_label}:{ov.source_label}",
                "analysis.allowed-unresolved-imports",
                "translated",
                ", ".join(ov.targets),
            )
        )
        return

    ov_rules: dict[str, str] = {}
    for key, val in ov.settings.items():
        if key == "disable_error_code":
            for code in _ensure_list(val):
                _map_mypy_error_code(code, "ignore", f"{src_label}:{ov.source_label}", ov_rules, report)
        elif key == "enable_error_code":
            for code in _ensure_list(val):
                _map_mypy_error_code(code, "error", f"{src_label}:{ov.source_label}", ov_rules, report)
        elif key in MYPY_BOOL_FLAG_TO_TY_RULE:
            ty_rule, when_true, when_false = MYPY_BOOL_FLAG_TO_TY_RULE[key]
            sev = when_true if bool(val) else when_false
            ov_rules[ty_rule] = sev
            report.items.append(
                ReportItem(
                    f"{src_label}:{ov.source_label}:{key}={val}",
                    f"overrides.rules.{ty_rule}={sev}",
                    "translated",
                )
            )
        elif key in MYPY_UNSUPPORTED_OR_IMPLICIT:
            report.items.append(
                ReportItem(
                    f"{src_label}:{ov.source_label}:{key}={val}",
                    "(guidance)",
                    "guidance",
                    MYPY_UNSUPPORTED_OR_IMPLICIT[key],
                )
            )
        else:
            report.items.append(
                ReportItem(
                    f"{src_label}:{ov.source_label}:{key}={val}",
                    "(unmapped)",
                    "unmapped",
                    f"Unsupported mypy override key {key!r}",
                )
            )

    if ov_rules and ov.targets:
        globs: list[str] = []
        for mod in ov.targets:
            g, approx = mypy_module_to_glob(mod)
            globs.append(g)
            if approx:
                report.warnings.append(
                    f"Mypy module override {mod!r} mapped approximately to glob {g!r}; verify path matches your repo layout."
                )
        ty_cfg.overrides.append(TyOverride(include=globs, rules=ov_rules))


def _apply_pyright_config(cfg: SourceConfig, ty_cfg: TyConfig, report: MigrationReport) -> None:
    src_label = f"{cfg.origin.name}[{cfg.tool}]"
    venv_path: str | None = None
    venv_name: str | None = None

    for key, val in cfg.global_settings.items():
        if key == "pythonVersion":
            ver = normalize_python_version(val)
            if ver:
                ty_cfg.environment["python-version"] = ver
                report.items.append(
                    ReportItem(f"{src_label}:pythonVersion", "environment.python-version", "translated", ver)
                )
        elif key == "pythonPlatform":
            plat = normalize_platform(val)
            if plat:
                ty_cfg.environment["python-platform"] = plat
                report.items.append(
                    ReportItem(f"{src_label}:pythonPlatform", "environment.python-platform", "translated", plat)
                )
        elif key in {"extraPaths", "stubPath"}:
            paths = [val] if isinstance(val, str) else _ensure_list(val)
            if paths:
                existing = ty_cfg.environment.setdefault("extra-paths", [])
                _append_unique(existing, paths)
                report.items.append(
                    ReportItem(f"{src_label}:{key}", "environment.extra-paths", "translated", ", ".join(paths))
                )
        elif key == "typeshedPath":
            ty_cfg.environment["typeshed"] = str(val)
            report.items.append(
                ReportItem(f"{src_label}:typeshedPath", "environment.typeshed", "translated", str(val))
            )
        elif key == "venvPath":
            venv_path = str(val)
        elif key == "venv":
            venv_name = str(val)
        elif key == "include":
            items = _ensure_list(val)
            if items:
                existing = ty_cfg.src.setdefault("include", [])
                _append_unique(existing, items)
                report.items.append(
                    ReportItem(f"{src_label}:include", "src.include", "translated", ", ".join(items))
                )
        elif key in {"exclude", "ignore"}:
            items = _ensure_list(val)
            if items:
                existing = ty_cfg.src.setdefault("exclude", [])
                _append_unique(existing, items)
                report.items.append(
                    ReportItem(f"{src_label}:{key}", "src.exclude", "translated", ", ".join(items))
                )
        elif key.startswith("report"):
            _map_pyright_report(key, val, src_label, ty_cfg.rules, report)
        elif key in PYRIGHT_UNSUPPORTED_OR_IMPLICIT:
            report.items.append(
                ReportItem(
                    f"{src_label}:{key}={val}",
                    "(implicit / guidance)",
                    "guidance",
                    PYRIGHT_UNSUPPORTED_OR_IMPLICIT[key],
                )
            )
        elif key in {"extends", "defineConstant"}:
            report.items.append(
                ReportItem(
                    f"{src_label}:{key}",
                    "(unmapped)",
                    "unmapped",
                    f"Pyright option {key!r} has no direct ty equivalent.",
                )
            )
        else:
            report.items.append(
                ReportItem(
                    f"{src_label}:{key}={val}",
                    "(unmapped)",
                    "unmapped",
                    f"No direct ty equivalent for pyright setting {key!r}",
                )
            )

    if venv_path and venv_name:
        joined = str(Path(venv_path) / venv_name)
        ty_cfg.environment["python"] = joined
        report.items.append(
            ReportItem(f"{src_label}:venvPath+venv", "environment.python", "translated", joined)
        )
    elif venv_path or venv_name:
        report.items.append(
            ReportItem(
                f"{src_label}:venv",
                "environment.python",
                "guidance",
                "Provide both `venvPath` and `venv` or set `[tool.ty.environment].python` manually if using a non-standard `.venv` path.",
            )
        )

    for ov in cfg.overrides:
        ov_rules: dict[str, str] = {}
        for k, v in ov.settings.items():
            if k.startswith("report"):
                _map_pyright_report(k, v, f"{src_label}:{ov.source_label}", ov_rules, report)
            elif k == "extraPaths":
                paths = _ensure_list(v)
                if paths:
                    existing = ty_cfg.environment.setdefault("extra-paths", [])
                    _append_unique(existing, paths)
                    report.items.append(
                        ReportItem(
                            f"{src_label}:{ov.source_label}:extraPaths",
                            "environment.extra-paths",
                            "guidance",
                            "ty overrides only scope rules/src; extraPaths was merged into global `environment.extra-paths`.",
                        )
                    )
            elif k in PYRIGHT_UNSUPPORTED_OR_IMPLICIT:
                report.items.append(
                    ReportItem(
                        f"{src_label}:{ov.source_label}:{k}",
                        "(guidance)",
                        "guidance",
                        PYRIGHT_UNSUPPORTED_OR_IMPLICIT[k],
                    )
                )
            else:
                report.items.append(
                    ReportItem(
                        f"{src_label}:{ov.source_label}:{k}",
                        "(unmapped)",
                        "unmapped",
                        f"Unsupported pyright executionEnvironment option {k!r}",
                    )
                )

        if ov_rules:
            globs = [f"{t.rstrip('/')}/**" if not any(c in t for c in "*?") else t for t in ov.targets]
            ty_cfg.overrides.append(TyOverride(include=globs, rules=ov_rules))


def _map_pyright_report(
    key: str,
    val: Any,
    src_label: str,
    rules_dict: dict[str, str],
    report: MigrationReport,
) -> None:
    sev = normalize_pyright_severity(val)
    if sev is None:
        report.items.append(
            ReportItem(
                f"{src_label}:{key}={val}",
                "(unmapped)",
                "unmapped",
                f"Unrecognized pyright severity value {val!r}",
            )
        )
        return

    targets = PYRIGHT_REPORT_TO_TY_RULES.get(key)
    if targets:
        for rule in targets:
            rules_dict[rule] = sev
        report.items.append(
            ReportItem(
                f"{src_label}:{key}={val}",
                ", ".join(f"rules.{r}={sev}" for r in targets),
                "translated",
            )
        )
    else:
        report.items.append(
            ReportItem(
                f"{src_label}:{key}={val}",
                "(unmapped)",
                "unmapped",
                f"No direct ty rule mapping for pyright diagnostic {key!r}",
            )
        )
