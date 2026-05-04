# 02 — Architecture

## Four layers, one direction

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
                          │  Layer 3 — Agent loop (PydanticAI)   │
                          │  reviewer LLM drives investigation   │
                          │  via 5 tools                         │
                          └──────────────────┬───────────────────┘
                                             │ ReviewReport
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Layer 4 — Output                    │
                          │  Pydantic validation → CLI report    │
                          └──────────────────────────────────────┘
```

## Data flow in one paragraph

[run.py](../run.py) collects code (paste / file / folder), discovers `.py` files, and constructs a `CacheManager` for the target. Layer 1 builds or refreshes the cache. Layer 2 fires `pylint`, `bandit`, and `radon` concurrently via `asyncio.gather`. Layer 3 builds the initial prompt from `cache.get_map()` plus the three findings lists, hands it to a PydanticAI `Agent`, and streams its tool calls live. Layer 4 prints a formatted report from the validated `ReviewReport`.

## Per-layer files

| Layer | Files | Read more |
|---|---|---|
| 1 — Cache | [cache/ast_parser.py](../cache/ast_parser.py), [cache/summarizer.py](../cache/summarizer.py), [cache/cache_manager.py](../cache/cache_manager.py) | [03-cache-layer.md](03-cache-layer.md) |
| 2 — Static analysis | [tools/linter.py](../tools/linter.py), [tools/security.py](../tools/security.py), [tools/complexity.py](../tools/complexity.py) | [04-static-analysis.md](04-static-analysis.md) |
| 3 — Agent loop | [agent.py](../agent.py), [llm/provider.py](../llm/provider.py) | [05-agent-loop.md](05-agent-loop.md) |
| 4 — Output | [schema.py](../schema.py), [run.py](../run.py) | [06-output-layer.md](06-output-layer.md) |

## Two LLM roles

| Role | Used for | Default (Groq) |
|---|---|---|
| `SUMMARIZER_MODEL` | One-shot text completions in the cache layer (no tools). | `llama-3.1-8b-instant` |
| `REVIEWER_MODEL` | The agentic loop with tool use + structured output. | `groq:llama-3.3-70b-versatile` |

Provider auto-detection lives in [llm/provider.py](../llm/provider.py). Set any of `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `OLLAMA_HOST` and the right model strings get picked.
