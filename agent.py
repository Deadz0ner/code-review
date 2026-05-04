"""Agentic investigation loop built on PydanticAI.

The reviewer LLM (configured via `REVIEWER_MODEL` or auto-detected) receives:
  1. A compressed map of the project (from the cache layer).
  2. Findings from pylint, bandit, and radon.

It then drives its own context retrieval through five tools (get_file, get_lines,
get_imports, get_callers, list_files) until it can emit a validated `ReviewReport`.

PydanticAI handles the tool-use protocol, JSON-schema generation from type hints,
and automatic retries on output validation failures. We use `agent.iter()` to
stream nodes so the CLI can show live "step N" progress as the agent calls tools.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

from pydantic_ai import Agent, RunContext

from cache.cache_manager import CacheManager
from llm.provider import get_reviewer_model
from schema import ReviewReport


MAX_FILE_CHARS = 16000
MAX_CALLERS_RESULTS = 30


@dataclass
class ReviewDeps:
    """Dependencies passed into every tool call.

    Attributes:
        project_root: absolute path to the directory being reviewed.
        cache: CacheManager bound to that root.
        files: project-relative paths of all .py files included in the review.
    """

    project_root: Path
    cache: CacheManager
    files: List[str] = field(default_factory=list)


_SYSTEM_PROMPT = """You are a senior Python code reviewer. Your value is NOT in echoing what static tools already found — it is in INVESTIGATING further to add context the tools cannot provide.

You have five investigation tools:
  - get_file(path): full contents of a .py file
  - get_lines(path, start, end): a specific 1-indexed line range, with line numbers
  - get_imports(path): local (in-project) imports of a file
  - get_callers(function_name): all in-project call sites of a function, with surrounding context
  - list_files(): every .py file in the project

You will be given:
  1. A compressed codebase map (file paths + signatures + descriptions).
  2. Findings from pylint, bandit, and radon.

REQUIRED INVESTIGATION PROTOCOL — follow this before producing any output:

  STEP 1 — For EVERY bandit finding (security):
    a) Call get_lines() to read the exact lines flagged, with ~5 lines of context.
    b) Call get_callers() on the enclosing function to find who feeds it data.
    c) For each caller, decide if untrusted input reaches the vulnerable code.
       If yes, the caller's file is the ROOT CAUSE — record it in `root_cause`
       with file:line, and add the caller's file to `related_files`.

  STEP 2 — For EVERY radon finding (rank C/D/E/F):
    a) Call get_file() or get_lines() to read the function.
    b) Identify the specific structural cause (nested conditionals? mixed
       responsibilities? long if/elif chain?). Suggest a concrete refactor
       in `fix` (e.g. "split by HTTP method into _handle_get / _handle_post").

  STEP 3 — For pylint findings: bundle related style issues into ONE issue
    per file when they share a root cause. Don't emit one Issue per pylint hit.

  STEP 4 — Look for issues the tools MISSED. Skim the codebase map and any
    files you've already opened. Concrete examples:
      - functions taking untrusted input with no validation
      - hardcoded secrets, default credentials, or fallback secrets
      - silent except-pass blocks that swallow errors
      - mutable default arguments
      - resource leaks (DB connections, file handles)

You should make AT LEAST 3–5 tool calls before producing your final report on a
non-trivial codebase. Producing a report with zero investigation is a failure.

Severity guidance — be willing to use CRITICAL:
  - critical: SQL injection, command injection, auth bypass, RCE, hardcoded
    production secrets, broken cryptography in a security path. SQL injection
    in an authentication flow is ALWAYS critical, never medium.
  - high: weak crypto outside a hot security path, missing validation of
    untrusted input that reaches sensitive operations, real correctness bugs.
  - medium: noticeable defects, complexity that hurts maintainability, code
    smells with a real risk vector.
  - low: pure style/readability with no behavior implication.

Output requirements:
  - For each Issue, fill `root_cause` with `file:line` form whenever you traced
    it via get_callers. Don't put just a file path — include the line.
  - Fill `related_files` with every file you found involved.
  - `summary` should mention what you investigated, not just what the tools said.
"""


def build_agent() -> Agent[ReviewDeps, ReviewReport]:
    """Construct the reviewer agent and register all investigation tools."""
    model_str = get_reviewer_model()

    agent: Agent[ReviewDeps, ReviewReport] = Agent(
        model_str,
        deps_type=ReviewDeps,
        output_type=ReviewReport,
        system_prompt=_SYSTEM_PROMPT,
        retries=2,
        model_settings={"temperature": 0.1},
    )

    @agent.tool
    def get_file(ctx: RunContext[ReviewDeps], path: str) -> str:
        """Return the full contents of a .py file inside the project.

        Args:
            path: project-relative or absolute path to a .py file.

        Returns:
            The file contents (truncated if very large), or an ERROR string.
        """
        resolved = _resolve_in_project(ctx.deps, path)
        if resolved is None:
            return f"ERROR: file not found or outside project: {path}"
        if resolved.suffix != ".py":
            return f"ERROR: not a Python file: {path}"
        text = resolved.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_FILE_CHARS:
            head = text[:MAX_FILE_CHARS]
            return head + f"\n# ... (truncated; {len(text) - MAX_FILE_CHARS} more chars)"
        return text

    @agent.tool
    def get_lines(ctx: RunContext[ReviewDeps], path: str, start: int, end: int) -> str:
        """Return a 1-indexed inclusive line range with line numbers.

        Args:
            path: project-relative or absolute path to a .py file.
            start: first line, 1-indexed.
            end: last line, inclusive.

        Returns:
            Numbered lines joined by newlines, or an ERROR string.
        """
        resolved = _resolve_in_project(ctx.deps, path)
        if resolved is None:
            return f"ERROR: file not found: {path}"
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        s = max(1, int(start))
        e = min(len(lines), int(end))
        if s > e:
            return f"ERROR: invalid range {start}-{end} for file with {len(lines)} lines"
        return "\n".join(f"{i:5d}  {lines[i - 1]}" for i in range(s, e + 1))

    @agent.tool
    def get_imports(ctx: RunContext[ReviewDeps], path: str) -> List[str]:
        """Return local (in-project) imports for a file.

        Stdlib and third-party imports are filtered out — only modules whose
        top-level name matches a project file/directory are returned.
        """
        resolved = _resolve_in_project(ctx.deps, path)
        if resolved is None:
            return []
        try:
            tree = ast.parse(resolved.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return []

        project_modules = _project_module_names(ctx.deps)
        in_project: Set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in project_modules:
                        in_project.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    in_project.add(f"(relative import level {node.level}: {node.module or ''})")
                elif node.module:
                    top = node.module.split(".")[0]
                    if top in project_modules:
                        in_project.add(node.module)
        return sorted(in_project)

    @agent.tool
    def get_callers(ctx: RunContext[ReviewDeps], function_name: str) -> List[Dict[str, Any]]:
        """Search every .py file for calls to `function_name`.

        Heuristic: AST-based call-target detection. Matches both bare names
        (e.g. `login(...)`) and attribute calls ending in the name (e.g.
        `auth.login(...)`). Will miss calls through aliased imports or
        dynamic dispatch — those need manual investigation.

        Args:
            function_name: name to search for; if dotted (e.g. `Class.method`),
                only the last segment is used.

        Returns:
            Up to 30 hits, each with file, line, and 3 lines of surrounding context.
        """
        target = function_name.split(".")[-1]
        results: List[Dict[str, Any]] = []

        for rel in ctx.deps.files:
            path = ctx.deps.project_root / rel
            if not path.exists():
                continue
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source)
            except SyntaxError:
                continue
            source_lines = source.splitlines()

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                called = _resolve_call_name(node.func)
                if called is None:
                    continue
                if called == target or called.endswith(f".{target}"):
                    line_no = node.lineno
                    s = max(1, line_no - 1)
                    e = min(len(source_lines), line_no + 1)
                    context = "\n".join(
                        f"{i:5d}  {source_lines[i - 1]}" for i in range(s, e + 1)
                    )
                    results.append({"file": rel, "line": line_no, "context": context})
                    if len(results) >= MAX_CALLERS_RESULTS:
                        return results
        return results

    @agent.tool
    def list_files(ctx: RunContext[ReviewDeps]) -> List[str]:
        """Return every .py file in the project (project-relative paths)."""
        return list(ctx.deps.files)

    return agent


def build_initial_prompt(
    code_map: str,
    pylint_findings: List[Dict[str, Any]],
    bandit_findings: List[Dict[str, Any]],
    radon_findings: List[Dict[str, Any]],
) -> str:
    """Render the user prompt that kicks off the investigation.

    The code map plus three findings lists give the agent enough context to
    decide what to investigate further with its tools.
    """
    return (
        "## Codebase map\n"
        f"{code_map}\n\n"
        "## Static-analysis findings\n"
        f"PYLINT ({len(pylint_findings)} items):\n{json.dumps(pylint_findings[:50], indent=2)}\n\n"
        f"BANDIT ({len(bandit_findings)} items):\n{json.dumps(bandit_findings[:50], indent=2)}\n\n"
        f"RADON ({len(radon_findings)} items):\n{json.dumps(radon_findings[:50], indent=2)}\n\n"
        "Investigate these findings, trace root causes when relevant, then return your ReviewReport."
    )


async def run_investigation(
    agent: Agent[ReviewDeps, ReviewReport],
    initial_prompt: str,
    deps: ReviewDeps,
    on_step: Optional[Callable[[int, str], None]] = None,
) -> ReviewReport:
    """Stream the agent's investigation, calling `on_step` for each tool call.

    Uses PydanticAI's `agent.iter()` to walk nodes; CallToolsNode instances mark
    points where the LLM has produced one or more tool calls.

    Args:
        agent: the configured PydanticAI Agent.
        initial_prompt: the user prompt to send first.
        deps: runtime dependencies (project root, cache, file list).
        on_step: optional callback(step_index, tool_name) called as tools fire.

    Returns:
        The validated ReviewReport, with `investigation_steps` overwritten to
        the actual count of tool calls observed.
    """
    step = 0
    final_output: Optional[ReviewReport] = None

    async with agent.iter(initial_prompt, deps=deps) as run:
        async for node in run:
            if Agent.is_call_tools_node(node):
                parts = getattr(node, "model_response", None)
                parts = getattr(parts, "parts", []) if parts is not None else []
                for part in parts:
                    if not _is_tool_call_part(part):
                        continue
                    tool_name = getattr(part, "tool_name", "<unknown>")
                    # `final_result` is PydanticAI's internal mechanism for emitting
                    # structured output — not a user-facing investigation step.
                    if tool_name == "final_result":
                        continue
                    step += 1
                    if on_step:
                        on_step(step, tool_name)
        result = run.result

    if result is None:
        raise RuntimeError("Agent produced no final result")

    final_output = result.output
    if not isinstance(final_output, ReviewReport):
        raise RuntimeError(f"Agent returned unexpected output type: {type(final_output)}")

    final_output.investigation_steps = step
    return final_output


def _is_tool_call_part(part: Any) -> bool:
    """Detect ToolCallPart across PydanticAI versions without importing it directly."""
    kind = getattr(part, "part_kind", None)
    if kind == "tool-call":
        return True
    return part.__class__.__name__ == "ToolCallPart"


def _resolve_in_project(deps: ReviewDeps, path: str) -> Optional[Path]:
    """Resolve a path safely; reject anything outside the project root."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = deps.project_root / candidate
    try:
        candidate = candidate.resolve()
    except OSError:
        return None
    try:
        candidate.relative_to(deps.project_root)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _resolve_call_name(node: ast.AST) -> Optional[str]:
    """Best-effort textual representation of a call's target expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _resolve_call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _project_module_names(deps: ReviewDeps) -> Set[str]:
    """Top-level module names that resolve to in-project files or packages."""
    names: Set[str] = set()
    for rel in deps.files:
        first = rel.split("/", 1)[0]
        names.add(Path(first).stem)
    return names
