"""pylint subprocess wrapper.

pylint's exit code is a bitfield where any issue produces a non-zero exit.
We don't check the exit code — we just parse stdout as JSON.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List


async def run_pylint(files: List[Path], cwd: Path) -> List[Dict[str, Any]]:
    """Run pylint on `files` and return parsed findings.

    Args:
        files: absolute paths to .py files.
        cwd: working directory for the subprocess (the project root).

    Returns:
        A list of dicts with keys: file, line, message, symbol, type.
        Empty list if pylint is missing, fails, or finds nothing.
    """
    if not files:
        return []

    cmd = ["pylint", "--output-format=json", "--score=no", "--disable=C0114,C0115,C0116"] + [
        str(f) for f in files
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
    except FileNotFoundError:
        print("[warning] pylint not installed; skipping lint analysis")
        return []
    except Exception as exc:
        print(f"[warning] pylint failed to start: {exc}")
        return []

    stdout = stdout_b.decode("utf-8", errors="replace").strip() or "[]"
    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError:
        stderr = stderr_b.decode("utf-8", errors="replace")[:200]
        print(f"[warning] pylint output not JSON; stderr: {stderr}")
        return []

    findings: List[Dict[str, Any]] = []
    for item in raw:
        findings.append({
            "file": _relativize(item.get("path", ""), cwd),
            "line": item.get("line"),
            "message": item.get("message", ""),
            "symbol": item.get("symbol", ""),
            "type": item.get("type", ""),
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
