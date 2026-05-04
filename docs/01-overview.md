# 01 — Overview

## What this is

A CLI tool that runs an **agentic** code review on a Python project. The agent — an LLM with five investigation tools — receives the output of static analyzers and then drives its own follow-up: opening files, tracing function callers across modules, and producing a structured report.

## The problem it solves

Static analysis tools (`pylint`, `bandit`, `radon`) report **symptoms at the line they fire on**. They flag a SQL injection inside `auth.py`, but they can't tell you that the unsafe input actually entered the system three files away in `main.py`. A human reviewer would trace it back; this tool makes an LLM do that tracing automatically.

It also catches things the static tools miss entirely — timing-attack token comparisons, path traversal via `os.path.join`, user-controlled `shutil.rmtree` — because the agent reads the code in context, not just rule-by-rule.

## The approach in 4 bullets

1. **Cache layer** — parse every `.py` file once with `ast`, summarize undocumented functions with a cheap LLM, persist to `.review_cache.json` keyed by SHA-256.
2. **Static analysis** — run `pylint` + `bandit` + `radon` as subprocesses in parallel.
3. **Agent loop** — hand the cache map + findings to a capable LLM (PydanticAI). It calls `get_file`, `get_lines`, `get_imports`, `get_callers`, `list_files` until it can write a report.
4. **Output** — Pydantic validates the report structure and the CLI renders it.

## Who this is for

Engineers who want a reviewer that **traces root causes across files**, not just one that wraps an LLM around `pylint --json`. The cache layer makes it cheap to re-run on each commit; the agent layer makes the output actually useful.

## Where to read next

- Architecture and data flow → [02-architecture.md](02-architecture.md)
- What the tool does and explicitly does not do → [07-scope.md](07-scope.md)
- How to demo it → [09-demo-guide.md](09-demo-guide.md)
