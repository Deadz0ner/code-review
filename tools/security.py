"""bandit subprocess wrapper for security findings."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List


async def run_bandit(files: List[Path], cwd: Path) -> List[Dict[str, Any]]:
    """Run bandit on `files` and return parsed security findings.

    Args:
        files: absolute paths to .py files.
        cwd: working directory for the subprocess.

    Returns:
        A list of dicts with keys: file, line, issue_text, severity, confidence, issue_cwe.
        Empty list if bandit is missing, fails, or finds nothing.
    """
    if not files:
        return []

    cmd = ["bandit", "-f", "json", "-q"] + [str(f) for f in files]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, _ = await proc.communicate()
    except FileNotFoundError:
        print("[warning] bandit not installed; skipping security analysis")
        return []
    except Exception as exc:
        print(f"[warning] bandit failed to start: {exc}")
        return []

    stdout = stdout_b.decode("utf-8", errors="replace").strip() or "{}"
    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    findings: List[Dict[str, Any]] = []
    for item in raw.get("results", []) or []:
        cwe = item.get("issue_cwe") or {}
        cwe_id = cwe.get("id") if isinstance(cwe, dict) else cwe
        findings.append({
            "file": _relativize(item.get("filename", ""), cwd),
            "line": item.get("line_number"),
            "issue_text": item.get("issue_text", ""),
            "severity": (item.get("issue_severity") or "").lower(),
            "confidence": (item.get("issue_confidence") or "").lower(),
            "issue_cwe": cwe_id,
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
