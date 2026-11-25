"""Command-line interface for ty-migrate."""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ty_migrate import __version__
from ty_migrate.ignores import iter_python_files, rewrite_python_source
from ty_migrate.migrator import MigrationReport, migrate_configs
from ty_migrate.parsers import discover_configs
from ty_migrate.toml_emitter import render_ty_toml, upsert_pyproject_toml


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ty-migrate",
        description="Migrate mypy and pyright/basedpyright configs and inline ignores to Astral's ty.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("."),
        help="Project root directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--from",
        dest="source_filter",
        choices=["auto", "mypy", "pyright", "basedpyright"],
        default="auto",
        help="Source type-checker config to migrate from (default: auto).",
    )
    parser.add_argument("--mypy-config", type=Path, default=None, help="Explicit mypy config path.")
    parser.add_argument("--pyright-config", type=Path, default=None, help="Explicit pyright config path.")
    parser.add_argument("--pyproject", type=Path, default=None, help="Explicit pyproject.toml path.")
    parser.add_argument(
        "--target",
        choices=["auto", "pyproject", "ty-toml"],
        default="auto",
        help="Output target format: pyproject ([tool.ty.*]) or ty-toml (standalone ty.toml).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Explicit output file path.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print generated ty TOML configuration to stdout instead of writing files.",
    )
    parser.add_argument(
        "--rewrite-ignores",
        action="store_true",
        help="Rewrite # type: ignore[...] and # pyright: ignore[...] comments in .py/.pyi files to # ty: ignore[...].",
    )
    parser.add_argument(
        "--rewrite-bare-ignores",
        action="store_true",
        help="Also rewrite bare # type: ignore / # pyright: ignore comments without error codes.",
    )
    parser.add_argument(
        "--unmapped-strategy",
        choices=["keep", "blanket"],
        default="keep",
        help="How to handle inline ignore comments containing unmapped codes (default: keep).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying any files.",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Print unified diffs for all proposed file changes.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print a detailed audit report of translated, guidance, and unmapped items.",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit migration result and audit report as JSON.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with code 3 if any settings or inline ignore codes remain unmapped.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run `ty check` after writing configuration (if `ty` is installed).",
    )
    return parser


def _resolve_target_path(
    root: Path,
    target: str,
    explicit_output: Path | None,
    pyproject_arg: Path | None,
) -> tuple[Path, bool]:
    """Return (output_path, is_pyproject)."""
    if explicit_output is not None:
        is_pyproject = explicit_output.name == "pyproject.toml"
        return explicit_output, is_pyproject

    pyproject_file = pyproject_arg or (root / "pyproject.toml")
    if target == "pyproject":
        return pyproject_file, True
    if target == "ty-toml":
        return root / "ty.toml", False

    # auto: prefer existing pyproject.toml, else ty.toml
    if pyproject_file.is_file():
        return pyproject_file, True
    return root / "ty.toml", False


def _format_report(report: MigrationReport) -> str:
    lines: list[str] = []
    lines.append("=== ty-migrate Audit Report ===")
    lines.append(f"Sources: {', '.join(report.sources) if report.sources else 'none'}")
    lines.append(
        f"Summary: {report.translated_count} translated, "
        f"{report.guidance_count} guidance/implicit, "
        f"{report.unmapped_count} unmapped"
    )

    for status, heading in (
        ("translated", "Translated"),
        ("guidance", "Guidance / Implicit in ty"),
        ("unmapped", "Unmapped (Action Required)"),
    ):
        subset = [i for i in report.items if i.status == status]
        if not subset:
            continue
        lines.append(f"\n[{heading}]")
        for item in subset:
            suffix = f" ({item.detail})" if item.detail else ""
            lines.append(f"  - {item.source} -> {item.target}{suffix}")

    if report.ignores_rewritten or report.ignores_unchanged or report.unmapped_ignore_codes:
        lines.append("\n[Inline Ignore Comments]")
        lines.append(f"  - Rewritten: {report.ignores_rewritten}")
        lines.append(f"  - Unchanged: {report.ignores_unchanged}")
        if report.unmapped_ignore_codes:
            for code, count in sorted(report.unmapped_ignore_codes.items()):
                lines.append(f"  - Unmapped code {code!r}: {count} occurrence(s)")

    if report.warnings:
        lines.append("\n[Warnings]")
        for w in report.warnings:
            lines.append(f"  - {w}")

    if report.files_modified:
        lines.append("\n[Files]")
        for f in report.files_modified:
            lines.append(f"  - {f}")

    return "\n".join(lines)


def _unified_diff(old: str, new: str, label: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.dir.resolve()

    configs = discover_configs(
        root,
        source_filter=args.source_filter,
        mypy_path=args.mypy_config,
        pyright_path=args.pyright_config,
        pyproject_path=args.pyproject,
    )

    if not configs:
        print(
            f"No mypy or pyright configuration found in {root}.",
            file=sys.stderr,
        )
        return 1

    ty_cfg, report = migrate_configs(configs)
    out_path, is_pyproject = _resolve_target_path(root, args.target, args.output, args.pyproject)
    toml_block = render_ty_toml(ty_cfg, pyproject_prefix=is_pyproject)

    if is_pyproject and out_path.is_file():
        old_cfg_text = out_path.read_text(encoding="utf-8")
        new_cfg_text = upsert_pyproject_toml(old_cfg_text, toml_block)
    else:
        old_cfg_text = out_path.read_text(encoding="utf-8") if out_path.is_file() else ""
        new_cfg_text = toml_block

    diffs: list[str] = []
    if old_cfg_text != new_cfg_text:
        report.files_modified.append(str(out_path))
        if args.diff:
            diffs.append(_unified_diff(old_cfg_text, new_cfg_text, out_path.name))
        if not args.dry_run and not args.stdout:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(new_cfg_text, encoding="utf-8")

    # Inline ignores pass
    if args.rewrite_ignores:
        for py_file in iter_python_files(root):
            src_text = py_file.read_text(encoding="utf-8")
            res = rewrite_python_source(
                src_text,
                py_file,
                rewrite_bare=args.rewrite_bare_ignores,
                unmapped_strategy=args.unmapped_strategy,
            )
            report.ignores_rewritten += res.rewritten_count
            report.ignores_unchanged += res.unchanged_count
            for code, cnt in res.unmapped_codes.items():
                report.unmapped_ignore_codes[code] = (
                    report.unmapped_ignore_codes.get(code, 0) + cnt
                )
            if res.changed:
                rel = str(py_file.relative_to(root)) if py_file.is_relative_to(root) else str(py_file)
                report.files_modified.append(str(py_file))
                if args.diff:
                    diffs.append(_unified_diff(res.original_text, res.new_text, rel))
                if not args.dry_run and not args.stdout:
                    py_file.write_text(res.new_text, encoding="utf-8")

    if args.json_output:
        payload = {
            "version": __version__,
            "output_path": str(out_path),
            "toml": toml_block,
            "sources": report.sources,
            "summary": {
                "translated": report.translated_count,
                "guidance": report.guidance_count,
                "unmapped": report.unmapped_count,
                "ignores_rewritten": report.ignores_rewritten,
                "ignores_unchanged": report.ignores_unchanged,
                "unmapped_ignore_codes": report.unmapped_ignore_codes,
            },
            "items": [
                {
                    "source": i.source,
                    "target": i.target,
                    "status": i.status,
                    "detail": i.detail,
                }
                for i in report.items
            ],
            "warnings": report.warnings,
            "files_modified": report.files_modified,
        }
        print(json.dumps(payload, indent=2))
    else:
        if args.stdout:
            sys.stdout.write(toml_block)
        if args.diff and diffs:
            sys.stdout.write("\n".join(diffs))
        if args.report:
            print(_format_report(report))
        elif not args.stdout and not args.diff:
            action = "Would write" if args.dry_run else "Wrote"
            print(f"{action} {out_path} ({report.translated_count} settings translated, {report.unmapped_count} unmapped).")
            if args.rewrite_ignores:
                print(
                    f"Inline ignores: {report.ignores_rewritten} rewritten, "
                    f"{report.ignores_unchanged} unchanged."
                )

    if args.verify and not args.dry_run and not args.stdout:
        ty_bin = shutil.which("ty")
        if ty_bin is None:
            print("`ty` binary not found on PATH; skipping --verify.", file=sys.stderr)
        else:
            proc = subprocess.run([ty_bin, "check", "--project", str(root)], check=False)
            if proc.returncode != 0:
                return proc.returncode

    if args.check and report.has_issues():
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
