"""Hash-keyed cache of AST + LLM-generated descriptions, persisted to .review_cache.json.

First run: walks the project, parses every .py file, runs the summarizer for any
undocumented modules/functions, writes the cache.

Later runs: re-hashes each file and only re-parses + re-summarizes files whose
hash has changed. Removes entries for files that no longer exist.

Public API:
    CacheManager(project_root)
        .build(files, on_progress=...)   # populate / refresh
        .get_map() -> str                # compressed text view of the codebase
        .get_file_entry(rel_path) -> dict
        .list_files() -> list[str]
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from cache.ast_parser import parse_file
from cache.summarizer import summarize_file


CACHE_FILENAME = ".review_cache.json"

_SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    "node_modules",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
}


def file_hash(path: Path) -> str:
    """Compute SHA-256 of a file's bytes (chunked, suitable for any size)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_python_files(root: Path) -> List[Path]:
    """Walk `root`, returning all .py files, excluding venvs and build outputs."""
    files: List[Path] = []
    for p in root.rglob("*.py"):
        if any(part in _SKIP_DIR_NAMES for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


class CacheManager:
    """Read/write/invalidate the project's .review_cache.json."""

    def __init__(self, project_root: Path) -> None:
        """Bind to a project root and load any existing cache file."""
        self.root: Path = project_root.resolve()
        self.cache_path: Path = self.root / CACHE_FILENAME
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load existing cache from disk; return {} on missing or corrupt file."""
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save(self) -> None:
        """Write the cache dict back to disk as pretty-printed JSON."""
        self.cache_path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _rel(self, path: Path) -> str:
        """Project-relative path string (forward-slashed for cache keys)."""
        try:
            rel = path.resolve().relative_to(self.root)
        except ValueError:
            return str(path)
        return rel.as_posix()

    def build(
        self,
        files: List[Path],
        on_progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Refresh the cache for `files`, parsing/summarizing only what's changed.

        Args:
            files: list of .py files to include in the cache.
            on_progress: optional callback(label, current, total) for live updates.
        """
        seen: set[str] = set()
        total = len(files)

        for idx, path in enumerate(files, 1):
            rel = self._rel(path)
            seen.add(rel)
            current_hash = file_hash(path)
            cached = self._data.get(rel)

            if cached and cached.get("hash") == current_hash:
                if on_progress:
                    on_progress(f"cached  {rel}", idx, total)
                continue

            if on_progress:
                on_progress(f"parsing {rel}", idx, total)

            parsed = parse_file(path)
            entry: Dict[str, Any] = {
                "hash": current_hash,
                "description": parsed["description"],
                "classes": parsed["classes"],
                "functions": parsed["functions"],
                "parse_error": parsed["parse_error"],
            }

            if on_progress:
                on_progress(f"summarizing {rel}", idx, total)

            try:
                summarize_file(rel, entry)
            except Exception as exc:
                if on_progress:
                    on_progress(f"summarizer warning ({rel}): {exc}", idx, total)
                if entry["description"] is None:
                    entry["description"] = "Python module."
                for f in entry["functions"]:
                    if f.get("docstring") is None:
                        f["docstring"] = f"Function `{f['name']}`."

            for f in entry["functions"]:
                f.pop("body", None)

            self._data[rel] = entry

        for rel in list(self._data.keys()):
            if rel not in seen:
                del self._data[rel]

        self._save()

    def get_map(self) -> str:
        """Render a compressed plain-text map of the codebase for the reviewer prompt.

        Format:
            <file path> — <file description>
              <function signature> | <function docstring (first line)>
              ...
        """
        lines: List[str] = []
        for rel in sorted(self._data.keys()):
            entry = self._data[rel]
            desc = (entry.get("description") or "").strip()
            lines.append(f"{rel} — {desc}" if desc else rel)
            for func in entry.get("functions", []):
                doc_raw = func.get("docstring") or ""
                doc_first = doc_raw.strip().splitlines()[0] if doc_raw.strip() else ""
                if doc_first:
                    lines.append(f"  {func['signature']} | {doc_first}")
                else:
                    lines.append(f"  {func['signature']}")
        return "\n".join(lines)

    def get_file_entry(self, rel_path: str) -> Optional[Dict[str, Any]]:
        """Return the cached entry for a project-relative file path, or None."""
        return self._data.get(rel_path)

    def list_files(self) -> List[str]:
        """Return all cached file paths (project-relative, sorted)."""
        return sorted(self._data.keys())
