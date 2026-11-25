"""Mappings from mypy and pyright/basedpyright error codes & settings to Astral ty."""

from __future__ import annotations

import re
from typing import Any, Iterable

from ty_migrate.ty_rules import TY_RULES

# Mypy error code -> tuple of corresponding ty rule names.
# Every target rule MUST exist in TY_RULES (verified by tests and runtime check).
MYPY_ERROR_CODE_TO_TY_RULES: dict[str, tuple[str, ...]] = {
    "abstract": ("abstract-class-instantiation",),
    "arg-type": ("invalid-argument-type",),
    "assert-type": ("type-assertion-failure", "assert-type-unspellable-subtype"),
    "assignment": ("invalid-assignment",),
    "attr-defined": ("missing-attribute",),
    "awaitable-return": ("invalid-await",),
    "call-arg": ("missing-argument", "unknown-argument", "too-many-positional-arguments"),
    "call-overload": ("no-matching-overload",),
    "comparison-overlap": ("redundant-condition",),
    "deprecated": ("deprecated",),
    "empty-body": ("invalid-implicit-return-in-function-with-stub-body",),
    "exit-return": ("invalid-implicit-return",),
    "explicit-override": ("invalid-explicit-override",),
    "final": ("override-of-final-method", "override-of-final-variable", "subclass-of-final-class"),
    "has-type": ("unresolved-reference",),
    "ignore-without-code": ("blanket-ignore-comment",),
    "import": ("import-not-found", "missing-module-member"),
    "import-not-found": ("import-not-found",),
    "import-untyped": ("import-not-found",),
    "index": ("not-subscriptable", "index-out-of-bounds", "invalid-typed-dict-key"),
    "method-assign": ("invalid-assignment",),
    "misc": ("invalid-declaration", "conflicting-declarations"),
    "mutable-override": ("incompatible-mutable-override",),
    "name-defined": ("unresolved-reference",),
    "no-overload-impl": ("missing-overload-implementation",),
    "no-redef": ("conflicting-declarations",),
    "operator": ("unsupported-operator", "not-callable", "not-iterable"),
    "overload-overlap": ("inconsistent-overload-implementation",),
    "override": ("incompatible-method-override", "incompatible-attribute-override"),
    "possibly-undefined": ("possibly-unresolved-reference",),
    "prop-decorator": ("incompatible-property-override",),
    "redundant-cast": ("redundant-cast",),
    "redundant-expr": ("redundant-condition",),
    "return": ("invalid-implicit-return",),
    "return-value": ("invalid-explicit-return",),
    "safe-super": ("invalid-super-argument", "unavailable-implicit-super-arguments"),
    "syntax": ("invalid-syntax-in-forward-annotation",),
    "truthy-bool": ("unsupported-bool-conversion",),
    "truthy-function": ("truthiness-test-of-callable",),
    "truthy-iterable": ("truthiness-test-of-iterable",),
    "type-abstract": ("abstract-class-instantiation",),
    "type-arg": ("missing-type-argument", "invalid-type-arguments"),
    "type-var": ("invalid-type-variable-bound", "invalid-type-variable-constraints"),
    "typeddict-item": ("missing-typed-dict-key", "invalid-typed-dict-key"),
    "typeddict-readonly-mutated": ("invalid-typed-dict-field",),
    "typeddict-unknown-key": ("unknown-typed-dict-constructor-key",),
    "union-attr": ("missing-union-attribute",),
    "unused-awaitable": ("unused-awaitable",),
    "unused-ignore": ("unused-ignore-comment", "unused-type-ignore-comment"),
    "used-before-def": ("unresolved-reference",),
    "valid-newtype": ("invalid-newtype",),
    "valid-type": ("invalid-type-form",),
    "var-annotated": ("invalid-declaration",),
}

# Pyright / Basedpyright report* setting & inline ignore code -> tuple of ty rules.
PYRIGHT_REPORT_TO_TY_RULES: dict[str, tuple[str, ...]] = {
    "reportAbstractUsage": ("abstract-class-instantiation", "abstract-method-call"),
    "reportArgumentType": ("invalid-argument-type",),
    "reportAssertAlwaysTrue": ("redundant-condition",),
    "reportAssignmentType": ("invalid-assignment",),
    "reportAttributeAccessIssue": ("missing-attribute", "invalid-attribute-access"),
    "reportCallInconsistentDecorator": ("inconsistent-overload-decorator",),
    "reportCallIssue": (
        "missing-argument",
        "unknown-argument",
        "too-many-positional-arguments",
        "not-callable",
    ),
    "reportDeprecated": ("deprecated",),
    "reportDuplicateImport": ("conflicting-declarations",),
    "reportFinal": (
        "override-of-final-method",
        "override-of-final-variable",
        "subclass-of-final-class",
    ),
    "reportFunctionMemberAccess": ("missing-attribute",),
    "reportGeneralTypeIssues": ("invalid-assignment", "invalid-argument-type", "invalid-type-form"),
    "reportImplicitOverride": ("missing-override-decorator",),
    "reportImportCycles": ("cyclic-class-definition",),
    "reportIncompatibleMethodOverride": ("incompatible-method-override",),
    "reportIncompatibleVariableOverride": (
        "incompatible-attribute-override",
        "incompatible-mutable-override",
    ),
    "reportInconsistentConstructor": ("invalid-dataclass-post-init",),
    "reportInconsistentOverload": ("inconsistent-overload-implementation",),
    "reportIndexIssue": ("not-subscriptable", "index-out-of-bounds"),
    "reportInvalidCast": ("disjoint-cast",),
    "reportInvalidStringEscapeSequence": ("escape-character-in-forward-annotation",),
    "reportInvalidStubStatement": ("invalid-implicit-return-in-function-with-stub-body",),
    "reportInvalidTypeArguments": ("invalid-type-arguments",),
    "reportInvalidTypeForm": ("invalid-type-form",),
    "reportInvalidTypeVarUse": ("invalid-type-variable-bound", "unbound-type-variable"),
    "reportMatchNotExhaustive": ("invalid-match-pattern",),
    "reportMissingImports": ("import-not-found",),
    "reportMissingModuleSource": ("import-not-found",),
    "reportMissingParameterType": ("invalid-declaration",),
    "reportMissingSuperCall": ("invalid-super-argument",),
    "reportMissingTypeArgument": ("missing-type-argument",),
    "reportMissingTypeStubs": ("import-not-found",),
    "reportNoOverloadImplementation": ("missing-overload-implementation",),
    "reportOperatorIssue": ("unsupported-operator",),
    "reportOptionalCall": ("not-callable",),
    "reportOptionalContextManager": ("invalid-context-manager",),
    "reportOptionalIterable": ("not-iterable",),
    "reportOptionalMemberAccess": ("missing-union-attribute", "possibly-missing-attribute"),
    "reportOptionalOperand": ("unsupported-operator",),
    "reportOptionalSubscript": ("not-subscriptable",),
    "reportOverlappingOverload": ("inconsistent-overload-implementation",),
    "reportPossiblyUnboundVariable": ("possibly-unresolved-reference",),
    "reportPropertyTypeMismatch": ("incompatible-property-override",),
    "reportRedeclaration": ("conflicting-declarations",),
    "reportReturnType": ("invalid-explicit-return", "invalid-implicit-return"),
    "reportSelfClsParameterName": ("invalid-init-type-variable",),
    "reportShadowedImports": ("possibly-missing-submodule",),
    "reportTypeCommentUsage": ("raw-string-type-annotation",),
    "reportTypedDictNotRequiredAccess": ("invalid-typed-dict-key", "missing-typed-dict-key"),
    "reportUnboundVariable": ("unresolved-reference",),
    "reportUndefinedVariable": ("unresolved-reference",),
    "reportUnnecessaryCast": ("redundant-cast",),
    "reportUnnecessaryComparison": ("redundant-condition",),
    "reportUnnecessaryIsInstance": ("redundant-condition",),
    "reportUnnecessaryTypeIgnoreComment": ("unused-type-ignore-comment", "unused-ignore-comment"),
    "reportUnsupportedDunderAll": ("unresolved-global",),
    "reportUnusedCoroutine": ("unused-awaitable",),
    "reportWildcardImportFromLibrary": ("missing-module-member",),
    # Basedpyright-specific popular diagnostics
    "reportIgnoreCommentWithoutRule": ("blanket-ignore-comment",),
    "reportUnannotatedClassAttribute": ("invalid-declaration",),
    "reportUnsafeMultipleInheritance": ("instance-layout-conflict",),
}

# Mypy boolean/value config flags that map directly to ty rule severities.
MYPY_BOOL_FLAG_TO_TY_RULE: dict[str, tuple[str, str, str]] = {
    # flag_name: (ty_rule, severity_when_true, severity_when_false)
    "ignore_missing_imports": ("import-not-found", "ignore", "error"),
    "warn_redundant_casts": ("redundant-cast", "warn", "ignore"),
    "warn_unused_ignores": ("unused-type-ignore-comment", "warn", "ignore"),
    "warn_unreachable": ("redundant-condition", "warn", "ignore"),
    "warn_return_any": ("unsound-return", "warn", "ignore"),
    "disallow_any_generics": ("missing-type-argument", "error", "ignore"),
    "disallow_subclassing_any": ("unsupported-dynamic-base", "error", "ignore"),
    "enable_incomplete_feature": ("experimental-syntax", "warn", "ignore"),
}

# Settings intentionally different or unsupported in ty, with concise migration guidance.
MYPY_UNSUPPORTED_OR_IMPLICIT: dict[str, str] = {
    "strict": (
        "ty has no single `strict` flag (its defaults are already strict); "
        "enable extra strict rules like `possibly-missing-attribute` or `unsound-return` in `[tool.ty.rules]` if desired."
    ),
    "check_untyped_defs": (
        "ty checks unannotated function bodies unconditionally (`check_untyped_defs` is always on)."
    ),
    "disallow_untyped_defs": (
        "ty does not have a rule requiring annotations on all functions yet."
    ),
    "disallow_incomplete_defs": (
        "ty does not have a partial-annotation enforcement rule yet."
    ),
    "disallow_untyped_calls": (
        "ty allows calling unannotated functions (inferring `Unknown` types)."
    ),
    "disallow_untyped_decorators": (
        "See `dynamic-function-decorator-return` in `[tool.ty.rules]` if you want stricter decorator return checks."
    ),
    "follow_imports": (
        "ty resolves workspace and environment imports automatically; use `[tool.ty.src]` or `allowed-unresolved-imports` for exclusions."
    ),
    "plugins": (
        "ty does not load mypy plugins, though it has built-in support for common libraries like dataclasses and Pydantic."
    ),
    "incremental": "ty manages caching and incremental analysis natively.",
    "cache_dir": "ty manages its cache internally.",
    "sqlite_cache": "ty manages its cache internally.",
    "pretty": "Mapped conceptually via `[tool.ty.terminal]` (`output-format = \"full\"`).",
    "show_error_codes": "ty always prints rule names in diagnostics.",
    "show_column_numbers": "ty always includes column locations.",
    "namespace_packages": "PEP 420 namespace packages are supported automatically by ty.",
    "explicit_package_bases": "Use `[tool.ty.environment].root` if your project has non-standard source roots.",
    "no_implicit_optional": "ty enforces PEP 484 non-implicit Optional unconditionally.",
    "strict_optional": "ty enforces strict Optional checking unconditionally.",
    "strict_equality": "See `redundant-condition` / `unsupported-operator` in `[tool.ty.rules]`.",
    "implicit_reexport": "ty follows typing stub export rules (`__all__` / explicit `as` re-exports) natively.",
    "no_implicit_reexport": "ty follows typing stub export rules (`__all__` / explicit `as` re-exports) natively.",
}

PYRIGHT_UNSUPPORTED_OR_IMPLICIT: dict[str, str] = {
    "typeCheckingMode": (
        "ty has no single `typeCheckingMode` preset; most checks are `error` by default. "
        "Review `[tool.ty.rules]` for optional strict rules (`possibly-missing-attribute`, `unsound-assignment`, etc.)."
    ),
    "analyzeUnannotatedFunctions": (
        "ty always analyzes unannotated function bodies."
    ),
    "strictListInference": "ty performs union inference for literals by default.",
    "strictDictionaryInference": "ty performs union inference for literals by default.",
    "strictSetInference": "ty performs union inference for literals by default.",
    "strictParameterNoneValue": "ty enforces PEP 484 non-implicit Optional unconditionally.",
    "useLibraryCodeForTypes": "ty uses source code when stubs are absent automatically.",
    "autoImportCompletions": "Editor LSP setting; not part of ty CLI checking.",
    "autoSearchPaths": "ty automatically detects `.`, `./src`, `./<pkg>`, and `./python` roots.",
}


def validate_rule_catalog() -> None:
    """Ensure every mapped target rule exists in TY_RULES."""
    for mapping in (MYPY_ERROR_CODE_TO_TY_RULES, PYRIGHT_REPORT_TO_TY_RULES):
        for src, targets in mapping.items():
            for rule in targets:
                if rule not in TY_RULES:
                    raise ValueError(f"Invalid ty rule {rule!r} mapped from {src!r}")
    for flag, (rule, _, _) in MYPY_BOOL_FLAG_TO_TY_RULE.items():
        if rule not in TY_RULES:
            raise ValueError(f"Invalid ty rule {rule!r} mapped from {flag!r}")


def normalize_python_version(raw: Any) -> str | None:
    """Normalize a Python version like '3.12.1' or 3.12 to '3.12'."""
    if raw is None:
        return None
    text = str(raw).strip()
    match = re.match(r"^(\d+\.\d+)", text)
    if match:
        return match.group(1)
    return text or None


def normalize_platform(raw: Any) -> str | None:
    """Normalize mypy/pyright platform names to ty's python-platform values."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    mapping = {
        "linux": "linux",
        "linux2": "linux",
        "win32": "windows",
        "windows": "windows",
        "darwin": "darwin",
        "macos": "darwin",
        "all": "all",
    }
    return mapping.get(text, text)


def normalize_pyright_severity(raw: Any) -> str | None:
    """Convert pyright severity (bool or string) into ty severity ('ignore'|'warn'|'error')."""
    if isinstance(raw, bool):
        return "error" if raw else "ignore"
    if isinstance(raw, str):
        val = raw.strip().lower()
        if val in {"none", "false", "ignore", "off"}:
            return "ignore"
        if val in {"warning", "warn", "information", "info", "hint"}:
            return "warn"
        if val in {"error", "true"}:
            return "error"
    return None


def mypy_module_to_glob(pattern: str) -> tuple[str, bool]:
    """Convert a mypy module pattern (e.g. 'tests.*' or 'pkg.mod') to a ty file glob.

    Returns (glob_pattern, is_approximate).
    """
    cleaned = pattern.strip()
    if not cleaned:
        return "**", True
    if cleaned == "*":
        return "**", False
    if cleaned.endswith(".*"):
        base = cleaned[:-2].replace(".", "/")
        return f"{base}/**", False
    if "*" in cleaned:
        return cleaned.replace(".", "/"), True
    path_part = cleaned.replace(".", "/")
    return f"{path_part}/**", True


def mypy_regex_exclude_to_globs(raw: Any) -> tuple[list[str], list[str]]:
    """Best-effort conversion of mypy regex `exclude` patterns to gitignore-style globs.

    Returns (converted_globs, unmapped_regexes).
    """
    patterns: list[str]
    if isinstance(raw, str):
        # Mypy INI exclude can be a single regex or (?x) verbose regex; split top-level | if simple
        patterns = [raw.strip()]
    elif isinstance(raw, list):
        patterns = [str(p).strip() for p in raw if str(p).strip()]
    else:
        return [], []

    globs: list[str] = []
    unmapped: list[str] = []

    for pat in patterns:
        # Unwrap simple non-capturing groups or ^/ anchors when safe
        candidates = _split_simple_regex_alternations(pat)
        for cand in candidates:
            converted = _single_regex_to_glob(cand)
            if converted is not None:
                globs.append(converted)
            else:
                unmapped.append(cand)

    return _dedupe_preserve_order(globs), unmapped


def _split_simple_regex_alternations(pat: str) -> list[str]:
    text = pat.strip()
    if text.startswith("(?x)"):
        return [text]
    if text.startswith("(") and text.endswith(")") and text.count("(") == 1 and text.count(")") == 1:
        text = text[1:-1]
    if "(" in text or "[" in text or "\\" in text:
        # Keep complex regexes intact unless all alternations are plain path tokens
        parts = text.split("|")
        if all(re.fullmatch(r"[\^]?[A-Za-z0-9_./*-]+[\$]?", p) for p in parts):
            return parts
        return [pat]
    return [p.strip() for p in text.split("|") if p.strip()]


def _single_regex_to_glob(cand: str) -> str | None:
    s = cand.strip()
    if not s:
        return None
    s = s.removeprefix("^").removesuffix("$")
    s = s.replace(r"\.", ".").replace(r"\/", "/")
    s = s.replace(".*", "**")
    # If regex metacharacters remain, don't guess silently
    if any(ch in s for ch in ("(", ")", "[", "]", "{", "}", "+", "?", "\\", "|")):
        return None
    if not s.startswith("/") and "/" in s and not s.endswith("/"):
        return s
    return s


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


validate_rule_catalog()
