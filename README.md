# code-review-agent

An agentic CLI code reviewer for Python projects. It builds a hash-keyed cache of every file's signatures and descriptions, runs `pylint` + `bandit` + `radon` in parallel, then hands the findings to an LLM that drives its own follow-up investigation through five tools and emits a Pydantic-validated report.

Built with **PydanticAI** for the agent loop and structured output. Configured for **Groq's free tier** out of the box; also supports Anthropic, OpenAI, Gemini, and Ollama.

---

## Architecture

```
                          ┌──────────────────────────────────────┐
                          │  Layer 1 — Cache                     │
   .py files ───────────► │  ast parser → cheap-LLM summarizer   │
                          │  → .review_cache.json (hash-keyed)   │
                          └──────────────────┬───────────────────┘
                                             │ compressed code map
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Layer 2 — Static analysis (parallel)│
                          │  pylint  ◇  bandit  ◇  radon         │
                          └──────────────────┬───────────────────┘
                                             │ findings
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Layer 3 — Agentic loop (PydanticAI) │
                          │  reviewer LLM drives investigation   │
                          │  via 5 tools:                        │
                          │    get_file, get_lines, get_imports, │
                          │    get_callers, list_files           │
                          └──────────────────┬───────────────────┘
                                             │ ReviewReport
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Layer 4 — Output                    │
                          │  Pydantic validation → CLI report    │
                          └──────────────────────────────────────┘
```

Two LLM roles, configured independently:

| Role | Used for | Default (Groq) |
|---|---|---|
| `SUMMARIZER_MODEL` | One-shot descriptions for undocumented files/functions | `llama-3.1-8b-instant` |
| `REVIEWER_MODEL` | The agentic loop with tool use and structured output | `groq:llama-3.3-70b-versatile` |

---

## Setup

```bash
cd code-review-agent-v2
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Configure a provider (pick one)

The agent auto-detects whichever of these env vars you set first. **Groq is recommended** — it's free and fast.

```bash
# Groq (recommended, free)
export GROQ_API_KEY=gsk_...

# OR Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# OR OpenAI
export OPENAI_API_KEY=sk-...

# OR Gemini
export GEMINI_API_KEY=...

# OR Ollama (local)
export OLLAMA_HOST=http://localhost:11434
```

### Override the auto-picked models (optional)

```bash
# Reviewer model uses PydanticAI's <provider>:<model> string
export REVIEWER_MODEL=groq:llama-3.3-70b-versatile
export REVIEWER_MODEL=anthropic:claude-sonnet-4-20250514
export REVIEWER_MODEL=openai:gpt-4o
export REVIEWER_MODEL=google-gla:gemini-1.5-pro

# Summarizer model is just a model name (uses an OpenAI-compatible client)
export SUMMARIZER_MODEL=llama-3.1-8b-instant       # Groq
export SUMMARIZER_MODEL=gpt-4o-mini                # OpenAI
export SUMMARIZER_MODEL=gemini-1.5-flash           # Gemini
export SUMMARIZER_MODEL=llama3                     # Ollama
```

---

## Usage

```bash
python run.py
```

Interactive prompt:

```
How do you want to provide code for review?
  [1] Paste code directly
  [2] File path (.py file)
  [3] Folder path

Choice [1/2/3]: 3
Path to folder: examples/buggy_app
```

Then watch each layer run, ending in a printed report.

### Demo targets

Two example projects ship with the tool:

| Target | What it shows |
|---|---|
| `examples/buggy_app/` | Compact 3-file example. SQL injection traced one hop from `auth.py` back to `api/routes.py:handle_login`. Good for a fast demo. |
| `examples/task_runner/` | Larger 8-file example. Showcases a **3-hop root-cause trace** (CLI argv → `scheduler.dispatch` → `storage.get_task_by_name`) plus issues the static tools miss: timing-attack token compare, path traversal, user-controlled `rm -rf`, TOCTOU window, default-secret fallback, and a bare `except` that swallows errors. The agent has to actually investigate to surface these — that's the point. |

---

## How the cache works

On first run, the cache layer:

1. Walks the project for every `.py` file (skipping `venv/`, `.git/`, `__pycache__/`, `dist/`, `build/`, etc.).
2. SHA-256 hashes each file.
3. AST-parses each file to extract module/class/function signatures, docstrings, and a `documented` flag.
4. Calls the cheap summarizer **only** for items with no docstring — never for already-documented code.
5. Writes everything to `.review_cache.json` in the project root.

On subsequent runs:

- For each file, current hash is compared to the cached hash.
- **Match** → entry is reused; no parsing, no summarizer call.
- **Hash changed or new file** → that one file is re-parsed and re-summarized.
- **File deleted** → its entry is dropped.

The cache file lives **inside the project being reviewed** (not in this tool's directory), so each project gets its own cache.

---

## Example output (with root-cause tracing)

```
============================================================
CODE REVIEW REPORT
============================================================
Files reviewed: 3  |  Agent steps: 6
Critical: 1  |  High: 1  |  Medium: 2  |  Low: 1

SUMMARY:
The buggy_app contains a critical SQL injection in auth.login that flows
from unsanitized request input via api/routes.py:handle_login. The auth
layer also uses MD5 for password hashing — broken for password storage.
handle_request has very high cyclomatic complexity and should be split
by HTTP method.

ISSUES:

[CRITICAL] security | auth.py:11
  String-concatenated SQL query allows arbitrary SQL injection via the
  `username` parameter.
  Root cause: input flows from api/routes.py:10 (handle_login) directly
  into login() without any sanitization or parameterization.
  Fix: use parameterized queries: cur.execute("SELECT id, password_hash
  FROM users WHERE username = ?", (username,))
  Related: api/routes.py

[HIGH] security | auth.py:23
  MD5 is unsuitable for password hashing — fast and cryptographically
  broken.
  Fix: replace with bcrypt or argon2 via the `passlib` or `argon2-cffi`
  package, and migrate stored hashes on next login.

[MEDIUM] complexity | api/routes.py:16
  handle_request has cyclomatic complexity 14 (rank D).
  Fix: split by HTTP method into _handle_get / _handle_post / _handle_delete.
...
```

The `Root cause` line is the agentic part — pylint and bandit flag the symptom inside `auth.py`, but the agent traced it back through `get_callers("login")` to `api/routes.py:handle_login` and reported the originating file as `related`.

---

## Limitations

- **Python only.** The cache layer parses with `ast`, so non-Python files in the project are ignored.
- **LLM-suggested fixes should be reviewed before applying.** The agent reads file slices, not the live runtime — it can be wrong. Treat the report like a senior reviewer's notes, not a patchset.
- **First run is slower.** The cache build runs the summarizer over every undocumented function. Subsequent runs are nearly instant for unchanged files. For a large repo, prewarm the cache before recording a demo.
- **`get_callers` is heuristic.** It uses AST call-target matching — it'll miss aliased imports (`from auth import login as do_login`) and dynamic dispatch (`getattr(mod, name)()`).
- **Tool-call rate limits.** Groq's free tier rate-limits multi-turn tool use; very large projects may need pacing or a different provider for the reviewer role.
