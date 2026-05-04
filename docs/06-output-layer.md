# 06 — Output layer

## The schema

[schema.py](../schema.py) defines two Pydantic models. PydanticAI uses them to (a) generate the tool-use schema the LLM is forced to fill, and (b) validate the response.

### `Issue`

| Field | Type | Notes |
|---|---|---|
| `file` | `str` | Project-relative path. |
| `line` | `Optional[int]` | 1-indexed; may be `None` for module-wide issues. |
| `severity` | `Literal["low", "medium", "high", "critical"]` | See rubric below. |
| `category` | `Literal["bug", "security", "complexity", "style"]` | What kind of problem. |
| `explanation` | `str` | What it is, why it matters, in plain language. |
| `fix` | `str` | Concrete suggested change. |
| `root_cause` | `Optional[str]` | If traced upstream — typically `file:line`. |
| `related_files` | `Optional[list[str]]` | Other files involved (callers, dependencies). |

### `ReviewReport`

`summary`, `issues: list[Issue]`, `total_files_reviewed`, `critical_count`, `high_count`, `investigation_steps`. Critical/high counts are also recomputed by [run.py](../run.py) when rendering, so the displayed numbers don't depend on the LLM doing arithmetic.

## Severity rubric

The system prompt is explicit so the LLM doesn't drift toward "everything is medium":

- **critical** — SQL injection, command injection, auth bypass, RCE, hardcoded production secrets, broken crypto in a security path. SQL injection in an auth flow is **always** critical.
- **high** — weak crypto outside a hot path, missing validation that reaches sensitive ops, real correctness bugs.
- **medium** — noticeable defects, complexity that hurts maintainability, code smells with a real risk vector.
- **low** — pure style with no behavior implication.

## CLI rendering

[run.py](../run.py) `_print_report` sorts issues by severity → file → line and prints each with:

```
[CRITICAL] security | auth.py:12
  String-concatenated SQL allows arbitrary injection via username.
  Root cause: api/routes.py:13
  Fix: use parameterized queries: cur.execute("... WHERE name = ?", (name,))
  Related: api/routes.py
```

`Root cause` and `Related` only render if the agent populated them. Empty optional fields are omitted, not printed as `None`.
