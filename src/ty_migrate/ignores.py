"""Tokenizer-safe rewriter for # type: ignore[...] and # pyright: ignore[...] comments."""

from __future__ import annotations

import io
import os
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from ty_migrate.mappings import (
    MYPY_ERROR_CODE_TO_TY_RULES,
    PYRIGHT_REPORT_TO_TY_RULES,
)

SKIP_DIRS: frozenset[str] = frozenset({
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".tox",
    ".nox",
    "node_modules",
    "dist",
    "build",
    ".eggs",
})

_IGNORE_RE = re.compile(
    r"^(?P<prefix>#\s*)(?P<tool>type|pyright)\s*:\s*ignore"
    r"(?:\s*\[\s*(?P<codes>[^\]]*)\s*\])?"
    r"(?P<tail>.*)$"
)


@dataclass
class IgnoreRewriteResult:
    """Result of scanning/rewriting a single Python file."""

    path: Path
    original_text: str
    new_text: str
    rewritten_count: int = 0
    unchanged_count: int = 0
    unmapped_codes: dict[str, int] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return self.original_text != self.new_text


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def rewrite_comment_token(
    comment_text: str,
    *,
    rewrite_bare: bool = False,
    unmapped_strategy: str = "keep",
) -> tuple[str, bool, list[str]]:
    """Rewrite a single Python comment token if it is a type/pyright ignore directive.

    Returns (new_comment, was_rewritten, unmapped_codes).
    """
    m = _IGNORE_RE.match(comment_text)
    if not m:
        return comment_text, False, []

    tool = m.group("tool")
    codes_raw = m.group("codes")
    tail = m.group("tail") or ""

    if codes_raw is None:
        if not rewrite_bare:
            return comment_text, False, []
        return f"# ty: ignore{tail}", True, []

    codes = [c.strip() for c in codes_raw.split(",") if c.strip()]
    if not codes:
        if not rewrite_bare:
            return comment_text, False, []
        return f"# ty: ignore{tail}", True, []

    # Preserve rules that already carry an explicit `ty:` prefix
    mapped_rules: list[str] = []
    unmapped: list[str] = []
    table = MYPY_ERROR_CODE_TO_TY_RULES if tool == "type" else PYRIGHT_REPORT_TO_TY_RULES

    for code in codes:
        if code.startswith("ty:"):
            mapped_rules.append(code.removeprefix("ty:"))
            continue
        targets = table.get(code)
        if targets:
            mapped_rules.extend(targets)
        else:
            unmapped.append(code)

    if unmapped and unmapped_strategy == "keep":
        return comment_text, False, unmapped

    deduped = _dedupe(mapped_rules)
    if deduped:
        new_comment = f"# ty: ignore[{', '.join(deduped)}]{tail}"
        return new_comment, True, unmapped

    if unmapped_strategy == "blanket":
        return f"# ty: ignore{tail}", True, unmapped

    return comment_text, False, unmapped


def rewrite_python_source(
    source: str,
    path: Path,
    *,
    rewrite_bare: bool = False,
    unmapped_strategy: str = "keep",
) -> IgnoreRewriteResult:
    """Safely rewrite inline ignore comments in Python source using tokenize."""
    lines = source.splitlines(keepends=True)
    if not lines:
        return IgnoreRewriteResult(path=path, original_text=source, new_text=source)

    # Map (line_no_1based, col_offset) -> replacement text
    edits: list[tuple[int, int, int, str]] = []
    rewritten_count = 0
    unchanged_count = 0
    unmapped_codes: dict[str, int] = {}

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return IgnoreRewriteResult(
            path=path,
            original_text=source,
            new_text=source,
        )

    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        new_comment, was_rewritten, unmapped = rewrite_comment_token(
            tok.string,
            rewrite_bare=rewrite_bare,
            unmapped_strategy=unmapped_strategy,
        )
        for code in unmapped:
            unmapped_codes[code] = unmapped_codes.get(code, 0) + 1

        if was_rewritten and new_comment != tok.string:
            rewritten_count += 1
            edits.append((tok.start[0], tok.start[1], tok.end[1], new_comment))
        elif _IGNORE_RE.match(tok.string):
            unchanged_count += 1

    if not edits:
        return IgnoreRewriteResult(
            path=path,
            original_text=source,
            new_text=source,
            rewritten_count=rewritten_count,
            unchanged_count=unchanged_count,
            unmapped_codes=unmapped_codes,
        )

    # Apply edits line-by-line (each comment token is single-line in Python)
    for line_no, start_col, end_col, replacement in reversed(edits):
        idx = line_no - 1
        line = lines[idx]
        lines[idx] = line[:start_col] + replacement + line[end_col:]

    return IgnoreRewriteResult(
        path=path,
        original_text=source,
        new_text="".join(lines),
        rewritten_count=rewritten_count,
        unchanged_count=unchanged_count,
        unmapped_codes=unmapped_codes,
    )


def iter_python_files(root: Path) -> list[Path]:
    """Recursively collect .py and .pyi files under root, skipping common build/venv dirs."""
    if root.is_file():
        return [root] if root.suffix in {".py", ".pyi"} else []

    collected: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for fname in sorted(filenames):
            if fname.endswith((".py", ".pyi")):
                collected.append(Path(dirpath) / fname)
    return collected
