# 09 — Demo guide

Concrete advice for recording the 3–5 minute submission video. The whole point is to show **real agentic behavior**, not just an LLM wrapper around `pylint`. Pick the parts of the run that visibly demonstrate that.

## Two demo targets

| Target | When to use it | What it shows |
|---|---|---|
| `examples/buggy_app/` | Quick demo, ~3 files, ~30s of agent runtime. | A single-hop trace: SQL injection in [auth.py](../examples/buggy_app/auth.py) → `handle_login` in [api/routes.py](../examples/buggy_app/api/routes.py). |
| `examples/task_runner/` | Full demo, 8 files, ~60–90s of agent runtime. | A 3-hop trace (CLI argv → `scheduler.dispatch` → `storage.get_task_by_name`) **plus** issues bandit/pylint don't catch: timing-attack token compare, path traversal, user-controlled `rm -rf`, TOCTOU window, default secret. |

Use `task_runner` for the recording. The longer trace + the agent-only finds make the difference between "this is just llm + lint" and "this is actually investigating."

## Suggested take order

1. **Frame the problem (~30s).** Show [examples/task_runner/storage.py](../examples/task_runner/storage.py) — bandit will flag the SQL injection here. Then show [examples/task_runner/main.py](../examples/task_runner/main.py) — argv goes straight in. Say: "static tools tell me the symptom is in storage, but the fix needs to happen at main.py."
2. **Show the architecture briefly (~30s).** Pull up [docs/02-architecture.md](02-architecture.md) and walk through the four-layer diagram. Don't read the whole file — just point at each box.
3. **Run it live (~90s).** `rm examples/task_runner/.review_cache.json` first so viewers see "Building code map..." narrate as each line prints:
   - `Building code map...` — "this is the cache layer parsing every file and asking a cheap LLM to describe the undocumented functions, just once."
   - `Running static analysis...` — "pylint, bandit, radon all in parallel."
   - `Agent investigating...` and the live `step N: tool_name` output — **this is the moment.** Pause and let the viewer see the agent calling `get_callers`, `get_file`, etc.
4. **Walk through the report (~45s).** Highlight:
   - The CRITICAL severity correctly assigned to SQL injection.
   - The `Root cause:` line tracing back to a different file than where bandit flagged it.
   - At least one issue bandit/pylint did NOT catch (timing attack, path traversal, `rm -rf`).
5. **One limitation + next step (~30s).** Pick from [docs/08-known-issues.md](08-known-issues.md) — the **silent cache-corruption fallback** or the **sequential summarizer calls** are both honest, real problems with concrete fixes.

## Things to point at on screen

- The live `step N` counter — visible proof of multi-tool investigation.
- The CRITICAL severity badge on the SQL injection.
- The `Root cause: main.py:23` (or similar) — the cross-file trace.
- An issue with no corresponding bandit finding — agent-only catch.

## Things to avoid

- Don't read the entire system prompt aloud. Mention that it's directive and move on.
- Don't try to demo all five tools individually. The live step counter shows them being used; that's enough.
- Don't claim the tool can apply fixes — it doesn't. Suggested fixes only. ([07-scope.md](07-scope.md).)

## If something goes sideways during recording

- **Agent makes 0 tool calls and goes straight to `final_result`.** Re-record. The directive prompt should prevent this on `llama-3.3-70b`, but if it happens, re-run — temperature is 0.1 not 0, so there's some variance.
- **Rate limit from Groq.** Wait a minute, retry. Or set `REVIEWER_MODEL=groq:qwen-2.5-coder-32b` as a fallback model with similar tool-use support.
- **No findings from one of the analyzers.** Almost always means the venv isn't activated. Check that the prompt says `(.venv)`.

## After recording

Submission checklist:
- [ ] Push the v2 folder to GitHub
- [ ] Make sure `.env` is gitignored (it is) — only `.env.example` should be committed
- [ ] Record video (Loom / YouTube unlisted / Drive)
- [ ] Submit both links by **2026-05-05 11:00 IST**
