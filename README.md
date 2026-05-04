# code-review-agent

An agentic CLI code reviewer for Python projects. It builds a hash-keyed cache of every file's signatures and descriptions, runs `pylint` + `bandit` + `radon` in parallel, then hands the findings to an LLM that drives its own follow-up investigation through five tools and emits a Pydantic-validated report.

Built with **PydanticAI** for the agent loop and structured output. Configured for **Groq's free tier** out of the box; also supports Anthropic, OpenAI, Gemini, and Ollama.

> Want to understand the project deeply? Read [docs/](docs/) — nine short, focused files cover architecture, each layer, scope, and known issues.

---

## Setup

```bash
cd code-review-agent-v2
python3 -m venv .venv
source .venv/bin/activate          # NOTE: source it, do NOT execute it
pip install -r requirements.txt
```

### Configure a provider

```bash
cp .env.example .env
# edit .env, paste your key (Groq is free)
```

`.env` is gitignored. The agent auto-detects whichever of these env vars is set first:

```
GROQ_API_KEY  >  ANTHROPIC_API_KEY  >  OPENAI_API_KEY  >  GEMINI_API_KEY  >  OLLAMA_HOST
```

To override the auto-picked model:

```bash
# in .env
REVIEWER_MODEL=groq:llama-3.3-70b-versatile      # default for Groq
REVIEWER_MODEL=anthropic:claude-sonnet-4-20250514
REVIEWER_MODEL=openai:gpt-4o
REVIEWER_MODEL=google-gla:gemini-1.5-pro

SUMMARIZER_MODEL=llama-3.1-8b-instant            # default for Groq
SUMMARIZER_MODEL=gpt-4o-mini
SUMMARIZER_MODEL=gemini-1.5-flash
SUMMARIZER_MODEL=llama3
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
Path to folder: examples/task_runner
```

Then watch each layer run live and end on a formatted report.

### Demo targets

Two example projects ship with the tool:

| Target | What it shows |
|---|---|
| [examples/buggy_app/](examples/buggy_app/) | Compact 3-file example. One-hop trace: SQL injection in `auth.py` → `handle_login` in `api/routes.py`. Fast demo (~30s). |
| [examples/task_runner/](examples/task_runner/) | Larger 8-file example. **3-hop trace** (CLI argv → `scheduler.dispatch` → `storage.get_task_by_name`) plus issues the static tools miss: timing-attack token compare, path traversal, user-controlled `rm -rf`, TOCTOU window, default secret. Best for video. |

---

## Architecture at a glance

```
.py files → cache (ast + cheap-LLM summaries, hash-keyed)
          → pylint + bandit + radon (parallel subprocesses)
          → reviewer LLM with 5 tools (PydanticAI agent loop)
          → Pydantic-validated ReviewReport → CLI
```

The five tools the agent drives: `get_file`, `get_lines`, `get_imports`, `get_callers`, `list_files`. See [docs/05-agent-loop.md](docs/05-agent-loop.md).

---

## Documentation

- [01-overview.md](docs/01-overview.md) — what + why + who
- [02-architecture.md](docs/02-architecture.md) — 4-layer diagram + data flow
- [03-cache-layer.md](docs/03-cache-layer.md) — AST + summarizer + hash invalidation
- [04-static-analysis.md](docs/04-static-analysis.md) — pylint/bandit/radon wrappers
- [05-agent-loop.md](docs/05-agent-loop.md) — PydanticAI agent + tool design + prompting
- [06-output-layer.md](docs/06-output-layer.md) — schema + severity rubric + CLI rendering
- [07-scope.md](docs/07-scope.md) — what we do and explicitly don't do
- [08-known-issues.md](docs/08-known-issues.md) — self-audit of this codebase
- [09-demo-guide.md](docs/09-demo-guide.md) — recording the submission video

---

## Limitations (short version — see [docs/07-scope.md](docs/07-scope.md) and [docs/08-known-issues.md](docs/08-known-issues.md) for full)

- **Python only.** No JS, Go, Rust.
- **LLM fixes should be reviewed before applying.** The tool suggests; it never patches.
- **First run is slower.** Subsequent runs reuse the cache for unchanged files.
- **`get_callers` is heuristic.** Misses aliased imports and dynamic dispatch.
- **Free-tier rate limits.** Groq caps requests per minute on multi-turn loops.
