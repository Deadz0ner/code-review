# 07 — Scope: what we do and don't do

## What we DO

- **Python only.** Parse `.py` files with the stdlib `ast` module. Class and function signatures, docstrings, line numbers.
- **Hash-keyed caching.** Per-file SHA-256 in `.review_cache.json`. Re-run is near-instant for unchanged files.
- **Cheap LLM summarization for undocumented code only.** Documented code is never sent to the summarizer.
- **Three static analyzers in parallel:** `pylint`, `bandit`, `radon`. Subprocess-based.
- **Agentic investigation loop** with five tools (`get_file`, `get_lines`, `get_imports`, `get_callers`, `list_files`).
- **Cross-file root-cause tracing** via `get_callers` + `get_imports`. Up to 3+ hops.
- **Pydantic-validated structured output** with auto-retry on validation failure.
- **Multi-provider:** Groq (default), Anthropic, OpenAI, Gemini, Ollama. Two roles configured independently.
- **Live CLI progress** showing each tool call as it fires.
- **`.env` support** for keys via `python-dotenv`.
- **Three input modes:** paste code directly, single file path, folder path.

## What we explicitly DON'T do

- **No non-Python languages.** No JS, TS, Go, Rust, Java. The cache layer would need a per-language parser.
- **No test execution.** We don't run `pytest`, don't read coverage reports, don't know which lines are tested.
- **No git awareness.** No `git log`, no `git blame`, no diff-based "what changed in this PR." The tool reviews a snapshot.
- **No automated fixes.** The agent suggests changes in the `fix` field. It does not edit files. Patch generation is out of scope.
- **No vector store / RAG over the codebase.** Context retrieval is purely AST-driven via the five tools; we don't embed files for semantic search.
- **No dependency / supply-chain scanning.** We don't read `requirements.txt`, `pyproject.toml`, or `pip-audit` output. Vulnerable transitive deps are invisible to us.
- **No secret-scanning of git history.** Bandit catches *literal* hardcoded secrets in source; secrets in the history are not in scope.
- **No cross-session memory.** Each run is independent. We don't track "this issue was deferred" or produce diffs against the last review.
- **No type checking.** `mypy` / `pyright` would be a useful fourth analyzer but isn't wired up.
- **No web fetches.** The agent can't look up CVEs or external docs while investigating.

## Constraints worth knowing

- **First run is slower.** Every undocumented function gets a summarizer call. On a 50-file repo with no docstrings, expect ~30–60 seconds. Subsequent runs are nearly instant.
- **Free-tier rate limits.** Groq's free tier has request-per-minute caps. Multi-turn agent loops on very large projects can hit them.
- **Heuristic caller search.** `get_callers` does AST call-target matching. It misses aliased imports (`from auth import login as do_login`) and dynamic dispatch (`getattr(mod, name)()`).
- **Truncated reads.** `get_file` truncates at 16KB. Larger files require `get_lines` for the rest.
