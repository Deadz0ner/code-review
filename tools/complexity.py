"""radon cyclomatic-complexity wrapper.

We only report functions with rank C, D, E, or F. Ranks A and B (cc <= 10) are
considered acceptable and excluded — including them in the report would create
noise the reviewer agent has to filter out anyway.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List


_HIGH_RANKS = {"C", "D", "E", "F"}


async def run_radon(files: List[Path], cwd: Path) -> List[Dict[str, Any]]:
    """Run `radon cc -j` on `files` and return high-complexity functions only.

    Args:
        files: absolute paths to .py files.
        cwd: working directory for the subprocess.

    Returns:
        A list of dicts with keys: file, function, complexity_score, rank, line.
        Empty list if radon is missing, fails, or finds nothing rank-C-or-worse.
    """
    if not files:
        return []

    cmd = ["radon", "cc", "-j"] + [str(f) for f in files]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, _ = await proc.communicate()
    except FileNotFoundError:
        print("[warning] radon not installed; skipping complexity analysis")
        return []
    except Exception as exc:
        print(f"[warning] radon failed to start: {exc}")
        return []

    stdout = stdout_b.decode("utf-8", errors="replace").strip() or "{}"
    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    findings: List[Dict[str, Any]] = []
    for file_path, items in raw.items():
        if not isinstance(items, list):
            continue
        rel = _relativize(file_path, cwd)
        for item in items:
            rank = item.get("rank", "")
            if rank not in _HIGH_RANKS:
                continue
            findings.append({
                "file": rel,
                "function": item.get("name", ""),
                "complexity_score": item.get("complexity"),
                "rank": rank,
                "line": item.get("lineno"),
            })
    return findings


def _relativize(file_path: str, root: Path) -> str:
    """Convert an absolute file path to a project-relative one if possible."""
    if not file_path:
        return file_path
    try:
        return Path(file_path).resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return file_path
