"""Fill in missing descriptions for undocumented files and functions.

We batch all undocumented items in a single file into one summarizer call to
minimize API requests. The summarizer is asked to return a strict JSON object;
we extract it defensively because cheap models sometimes wrap output in fences
or add preamble.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from llm.provider import call_summarizer


_SYSTEM_PROMPT = (
    "You are a code-documentation assistant. You write terse, accurate one-line "
    "descriptions of Python code. Return only the JSON object requested — no "
    "preamble, no markdown fences, no explanation."
)


def summarize_file(file_rel_path: str, file_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate `file_entry` to fill in any missing description and undocumented function docstrings.

    Args:
        file_rel_path: the file's project-relative path (used in the prompt for context).
        file_entry: the dict returned by `parse_file` (will be mutated in place).

    Returns:
        The same dict, with `description` filled in and `docstring` populated for any
        functions that had `documented=False`.
    """
    if file_entry.get("parse_error"):
        if file_entry.get("description") is None:
            file_entry["description"] = "File contains a syntax error and could not be parsed."
        return file_entry

    undocumented = [f for f in file_entry["functions"] if not f["documented"]]
    needs_file_desc = file_entry.get("description") is None

    if not undocumented and not needs_file_desc:
        return file_entry

    prompt = _build_prompt(file_rel_path, file_entry, undocumented, needs_file_desc)

    try:
        raw = call_summarizer(prompt, system=_SYSTEM_PROMPT)
    except Exception as exc:
        # Fall back to name-based descriptions; never break the cache build.
        _apply_fallback(file_entry, undocumented, needs_file_desc, reason=str(exc))
        return file_entry

    parsed = _safe_parse_json(raw)

    if needs_file_desc:
        desc = (parsed or {}).get("file") if parsed else None
        file_entry["description"] = (desc or _fallback_file_desc(file_entry)).strip()

    if undocumented:
        descs = (parsed or {}).get("functions") if parsed else None
        for i, func in enumerate(undocumented):
            generated: Optional[str] = None
            if isinstance(descs, list) and i < len(descs) and isinstance(descs[i], str):
                generated = descs[i].strip()
            func["docstring"] = generated or f"Undocumented function `{func['name']}`."

    return file_entry


def _build_prompt(
    file_rel_path: str,
    file_entry: Dict[str, Any],
    undocumented: List[Dict[str, Any]],
    needs_file_desc: bool,
) -> str:
    """Assemble a single batched prompt covering both file-level and function-level summaries."""
    parts: List[str] = [f"File: {file_rel_path}", ""]

    if needs_file_desc:
        sigs = [f["signature"] for f in file_entry["functions"]]
        parts.append("TASK A — write ONE sentence (<=20 words) describing what this file does.")
        parts.append("Function signatures present in the file:")
        for s in sigs:
            parts.append(f"  - {s}")
        parts.append("")

    if undocumented:
        parts.append(
            "TASK B — for each function below, write ONE sentence (<=15 words) "
            "describing what it does."
        )
        parts.append("")
        for i, func in enumerate(undocumented):
            parts.append(f"--- Function index {i} ---")
            parts.append(f"Signature: {func['signature']}")
            parts.append("Body:")
            parts.append(func.get("body", ""))
            parts.append("")

    parts.append("Return a single JSON object with these keys:")
    if needs_file_desc:
        parts.append('  "file": "<your sentence for TASK A>"')
    if undocumented:
        parts.append(
            '  "functions": ["<sentence for index 0>", "<sentence for index 1>", ...]'
        )
    parts.append("Return ONLY the JSON. No markdown. No commentary.")
    return "\n".join(parts)


def _safe_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON extraction from LLM output (strips fences, finds inner objects)."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _fallback_file_desc(file_entry: Dict[str, Any]) -> str:
    """Construct a minimal file description from the first few function names."""
    names = [f["name"] for f in file_entry.get("functions", [])][:3]
    if names:
        return f"Module containing {', '.join(names)}."
    return "Python module."


def _apply_fallback(
    file_entry: Dict[str, Any],
    undocumented: List[Dict[str, Any]],
    needs_file_desc: bool,
    reason: str,
) -> None:
    """When the summarizer call fails, populate descriptions from names so the cache is still usable."""
    if needs_file_desc:
        file_entry["description"] = _fallback_file_desc(file_entry)
    for func in undocumented:
        func["docstring"] = f"Undocumented function `{func['name']}`."
    file_entry["_summarizer_warning"] = reason
