# 08 — Known issues in this codebase

These are issues a careful human reviewer would call out in `code-review-agent-v2/` itself. They're listed here partly as honesty, and partly as a useful "what would I improve next?" answer for the demo video.

**Important:** the agent, when run on its own source, would catch almost none of these. They're architectural / UX / performance / robustness issues that don't show up in `pylint`, `bandit`, or `radon`, and that don't surface from cross-file tracing either. The agent is good at finding bugs **in** code; it's blind to bugs **in the system around** the code.

## Robustness

### Silent cache corruption fallback
[cache/cache_manager.py:67](../cache/cache_manager.py#L67) — `_load()` returns `{}` on `JSONDecodeError`. A corrupted `.review_cache.json` silently triggers full re-summarization (potentially expensive, all undocumented functions re-sent to the LLM) with no warning. Should at least log the corruption.

### No timeout / no retry on LLM calls
[llm/provider.py:104](../llm/provider.py#L104) — `call_summarizer` has no `timeout=` set on the OpenAI client and no retry on transient errors. A flaky Groq response either hangs or falls back to placeholder descriptions when a one-shot retry would have succeeded.

### Schema fields without defaults
[schema.py](../schema.py) — `total_files_reviewed`, `critical_count`, `high_count`, `investigation_steps` are required `int` fields. If the LLM omits any, validation fails and PydanticAI consumes a retry budget that could have been spent on real corrections. Defaults of `0` would be more robust.

## Performance

### Sequential summarizer calls
[cache/cache_manager.py:107](../cache/cache_manager.py#L107) — `build()` calls `summarize_file` once per file, sequentially. On a 50-file project with many undocumented functions, that's 50 round-trips back-to-back. `asyncio.gather` over a per-file async wrapper would parallelize cache builds significantly.

### Re-parsing on every `get_callers`
[agent.py](../agent.py) — `get_callers` AST-walks every project file on every invocation. Five caller queries against a 100-file project = 500 file reads. A simple in-memory cache of parsed ASTs (keyed by file hash) would be a meaningful win on larger projects.

## UX

### No preflight check for analyzer binaries
[run.py](../run.py) — if `python run.py` is invoked outside an activated venv, `pylint` / `bandit` / `radon` aren't on `PATH`, all three subprocess wrappers print `[warning] X not installed; skipping`, the agent gets empty findings, and the user sees a misleadingly thin report. A startup check for the three binaries with a clear "activate your venv" message would prevent this.

### `setup.py`-style false positives in `_project_module_names`
[agent.py](../agent.py) `_project_module_names` — derives module names from `Path(parts[0]).stem`. For a project with `setup.py` at root, "setup" becomes a "project module," so any `import setup` (which would be unusual but legal) would show up as a local import. Niche but real.

## Output quality

### Bandit low-confidence noise passes through unfiltered
[tools/security.py](../tools/security.py) — bandit's `confidence: low` findings are often false positives (e.g. it flags any string starting with `/tmp/` even when it's just a default config value). They're included without filtering, and the agent has to triage them. A confidence-threshold flag with a sensible default would tighten the prompt.

### `related_files` over-reach
Observed during testing: the agent sometimes lists a file in `related_files` because it called `get_file()` on it during investigation, even when the file wasn't actually involved in the issue. The system prompt should require a one-sentence justification per related file, or the model should be instructed to leave it empty unless the file is in the trace.

## What's NOT here

- Security issues in this codebase (there genuinely aren't any major ones — no SQL, no eval, no hardcoded secrets, env-var driven config).
- Test coverage gaps (tests are out of scope per the spec).
- Large-scale refactors (the layout is the layout the spec asked for).
