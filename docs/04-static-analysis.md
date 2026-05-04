# 04 — Static analysis

## Three tools, three jobs

| Tool | What it catches | Wrapper |
|---|---|---|
| `pylint` | Style, code smells, unused imports/args, too-many-branches, etc. | [tools/linter.py](../tools/linter.py) |
| `bandit` | Security issues — SQL injection, weak crypto, hardcoded passwords (CWE-mapped). | [tools/security.py](../tools/security.py) |
| `radon` | Cyclomatic complexity per function. | [tools/complexity.py](../tools/complexity.py) |

## Why subprocess and not the Python API

Each tool ships a Python API but they conflict on dependency versions, swallow stdout into their own loggers, and break across releases. Calling each as a subprocess with `--output-format=json` (or `-f json` / `-j`) gives:

- version isolation (we just need them on `PATH`)
- clean parseable output
- graceful degradation: if any tool isn't installed, the wrapper prints a warning and returns `[]`

## What the wrappers normalize

Each wrapper returns a list of dicts with predictable keys. The most important normalization step is **path relativization**: bandit emits absolute paths, pylint emits whatever you passed in, radon uses a different layout. All three are converted to project-relative paths via a small `_relativize` helper so the agent's prompt is consistent and the report's `file` field is always clickable from the project root.

## Parallelism

[run.py](../run.py) fires all three with `asyncio.gather`:

```python
pylint_findings, bandit_findings, radon_findings = await asyncio.gather(
    run_pylint(files, project_root),
    run_bandit(files, project_root),
    run_radon(files, project_root),
)
```

Wall-clock time = max of the three, not sum. On a small project this is sub-second.

## Tuning

- **radon**: only ranks **C, D, E, F** are returned. A and B (cc ≤ 10) would be noise that the agent then has to filter out anyway.
- **pylint**: `--disable=C0114,C0115,C0116` turns off "missing-docstring" warnings since the cache layer already tracks documentation.
- **bandit**: no filtering — all findings pass through with their `severity` and `confidence` fields, leaving the agent to triage low-confidence noise.

## Failure mode

If a tool's binary is missing, the wrapper prints `[warning] X not installed; skipping ...` and returns `[]`. The pipeline keeps going — the agent just sees fewer findings. Most often, this happens when `python run.py` is run **outside** the venv: the binaries are at `.venv/bin/pylint` etc., and only an activated venv puts those on `PATH`.
