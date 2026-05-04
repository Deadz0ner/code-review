# 05 — Agent loop

## Why PydanticAI

The "bonus" framework named in the assignment, and the right tool for this shape of problem:

- it generates the JSON schema for tool calls **from Python type hints**, no manual schema authoring
- it validates the final output against a Pydantic model and **auto-retries** on validation failure
- it speaks a uniform `<provider>:<model>` model string across Groq / Anthropic / OpenAI / Gemini
- `agent.iter()` exposes the run as a stream of nodes, which is what powers the live "step N" CLI updates

## The five tools

All defined in [agent.py](../agent.py) inside `build_agent()`. Each is a regular Python function decorated with `@agent.tool`; PydanticAI infers its schema from the type hints.

| Tool | Returns | Why the agent needs it |
|---|---|---|
| `get_file(path)` | full file text | Read a flagged file in full. |
| `get_lines(path, start, end)` | numbered line range | Cheap targeted reads, no need to spend tokens on a whole file. |
| `get_imports(path)` | local imports only | Decide which module to investigate next. Stdlib/third-party filtered. |
| `get_callers(function_name)` | up to 30 hits with file, line, context | The trace primitive. AST-based, matches bare names and attribute calls. |
| `list_files()` | every `.py` in the project | Lets the agent enumerate when the map alone isn't enough. |

`_resolve_in_project` is the path-safety check used by `get_file` and `get_lines` — it rejects path traversal and anything outside `project_root`.

## The system prompt

In [agent.py](../agent.py), `_SYSTEM_PROMPT` is intentionally **directive**, not soft. Earlier versions used phrasing like "investigate the findings, be efficient." With Groq's `llama-3.3-70b-versatile`, that produced zero tool calls — the model went straight to the final answer. The fix was to replace soft guidance with a **REQUIRED INVESTIGATION PROTOCOL** of explicit STEPs (one per tool category) plus concrete severity examples ("SQL injection in an authentication flow is ALWAYS critical, never medium").

Stronger models (Claude Sonnet, GPT-4) work fine with subtler prompts. Open-tier models need the imperative version.

## The loop

Driven by `run_investigation()` in [agent.py](../agent.py):

```python
async with agent.iter(initial_prompt, deps=deps) as run:
    async for node in run:
        if Agent.is_call_tools_node(node):
            for part in node.model_response.parts:
                if part is a tool call and tool_name != "final_result":
                    step += 1
                    on_step(step, tool_name)
    result = run.result
```

`final_result` is filtered because it's PydanticAI's internal mechanism for emitting structured output — counting it would inflate `investigation_steps` by one and clutter the live progress.

PydanticAI handles the message-shuffling: it sends the prompt, parses tool calls out of the model response, executes the tool, sends the result back, and repeats until the model emits a final result that validates against `ReviewReport`.

## Live progress

Every tool call prints a line like:

```
Agent investigating...
  step 1: get_lines
  step 2: get_callers
  step 3: get_file
  ...
```

The agent's `investigation_steps` field on the final `ReviewReport` is **overwritten** with the actual observed count, not the model's self-report (which can drift).
