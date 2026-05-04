"""Interactive CLI for the code-review-agent.

Asks the user how to provide code (paste / file / folder), normalizes that into
a project root, then runs the four-layer pipeline:

    cache build (parse + summarize) → static analysis (parallel) → agent loop → report
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

# Load .env from the project root before any module reads os.getenv().
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from agent import ReviewDeps, build_agent, build_initial_prompt, run_investigation  # noqa: E402
from cache.cache_manager import CacheManager, discover_python_files  # noqa: E402
from schema import ReviewReport  # noqa: E402
from tools.complexity import run_radon  # noqa: E402
from tools.linter import run_pylint  # noqa: E402
from tools.security import run_bandit  # noqa: E402


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _prompt_input_choice() -> Tuple[Path, bool]:
    """Ask the user how to provide code; return (project_root, is_temp_dir)."""
    print()
    print("How do you want to provide code for review?")
    print("  [1] Paste code directly")
    print("  [2] File path (.py file)")
    print("  [3] Folder path")
    print()

    while True:
        choice = input("Choice [1/2/3]: ").strip()
        if choice in {"1", "2", "3"}:
            break
        print("Please enter 1, 2, or 3.")

    if choice == "1":
        return _collect_pasted_code(), True
    if choice == "2":
        return _collect_single_file(), True
    return _collect_folder(), False


def _collect_pasted_code() -> Path:
    """Read multi-line pasted code, return a temp project root containing it."""
    print()
    print("Paste your Python code. End with a single line containing 'END':")
    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    if not lines:
        print("No code provided. Exiting.")
        sys.exit(1)
    tmp = Path(tempfile.mkdtemp(prefix="code_review_"))
    (tmp / "snippet.py").write_text("\n".join(lines), encoding="utf-8")
    return tmp


def _collect_single_file() -> Path:
    """Prompt for a .py file path; copy it into a temp project root."""
    path_str = input("Path to .py file: ").strip()
    src = Path(path_str).expanduser().resolve()
    if not src.exists() or src.suffix != ".py":
        print(f"Not a valid .py file: {src}")
        sys.exit(1)
    tmp = Path(tempfile.mkdtemp(prefix="code_review_"))
    shutil.copy2(src, tmp / src.name)
    return tmp


def _collect_folder() -> Path:
    """Prompt for a folder; validate it exists and contains .py files."""
    path_str = input("Path to folder: ").strip()
    folder = Path(path_str).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"Not a valid folder: {folder}")
        sys.exit(1)
    return folder


async def _run_pipeline(project_root: Path) -> ReviewReport:
    """Run cache → analysis → agent and return the validated report."""
    files = discover_python_files(project_root)
    if not files:
        print(f"No .py files found under {project_root}.")
        sys.exit(1)

    cache = CacheManager(project_root)
    is_first_run = not cache.cache_path.exists()
    print()
    print("Building code map..." if is_first_run else "Updating cache...")

    def _cache_progress(label: str, current: int, total: int) -> None:
        print(f"  [{current}/{total}] {label}")

    cache.build(files, on_progress=_cache_progress)

    print()
    print("Running static analysis (pylint + bandit + radon, parallel)...")
    pylint_findings, bandit_findings, radon_findings = await asyncio.gather(
        run_pylint(files, project_root),
        run_bandit(files, project_root),
        run_radon(files, project_root),
    )
    print(
        f"  pylint: {len(pylint_findings)} | "
        f"bandit: {len(bandit_findings)} | "
        f"radon: {len(radon_findings)}"
    )

    print()
    print("Agent investigating...")
    agent = build_agent()
    relative_files = [str(f.resolve().relative_to(project_root.resolve()).as_posix()) for f in files]
    deps = ReviewDeps(
        project_root=project_root.resolve(),
        cache=cache,
        files=relative_files,
    )
    initial_prompt = build_initial_prompt(
        cache.get_map(),
        pylint_findings,
        bandit_findings,
        radon_findings,
    )

    def _on_step(step: int, tool_name: str) -> None:
        print(f"  step {step}: {tool_name}")

    report = await run_investigation(agent, initial_prompt, deps, on_step=_on_step)

    if not report.total_files_reviewed:
        report.total_files_reviewed = len(files)

    return report


def _print_report(report: ReviewReport) -> None:
    """Render the review report to stdout in the spec's format."""
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in report.issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1

    print()
    print("=" * 60)
    print("CODE REVIEW REPORT")
    print("=" * 60)
    print(
        f"Files reviewed: {report.total_files_reviewed}  |  "
        f"Agent steps: {report.investigation_steps}"
    )
    print(
        f"Critical: {counts['critical']}  |  "
        f"High: {counts['high']}  |  "
        f"Medium: {counts['medium']}  |  "
        f"Low: {counts['low']}"
    )
    print()
    print("SUMMARY:")
    print(report.summary)
    print()

    if not report.issues:
        print("ISSUES: none found.")
        return

    print("ISSUES:")
    print()
    sorted_issues = sorted(
        report.issues,
        key=lambda i: (SEVERITY_ORDER.get(i.severity, 99), i.file, i.line or 0),
    )
    for issue in sorted_issues:
        loc = f"{issue.file}:{issue.line}" if issue.line else issue.file
        print(f"[{issue.severity.upper()}] {issue.category} | {loc}")
        print(f"  {issue.explanation}")
        if issue.root_cause:
            print(f"  Root cause: {issue.root_cause}")
        print(f"  Fix: {issue.fix}")
        if issue.related_files:
            print(f"  Related: {', '.join(issue.related_files)}")
        print()


def main() -> None:
    """CLI entry point."""
    project_root, is_temp = _prompt_input_choice()
    try:
        report = asyncio.run(_run_pipeline(project_root))
        _print_report(report)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    finally:
        if is_temp:
            shutil.rmtree(project_root, ignore_errors=True)


if __name__ == "__main__":
    main()
