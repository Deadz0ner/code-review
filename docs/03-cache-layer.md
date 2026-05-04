# 03 — Cache layer

## Why it exists

The agent's initial prompt needs a bird's-eye view of the codebase: what files exist, what functions are inside, and a one-line description of each. Generating those descriptions for every undocumented function costs tokens. We pay that cost **once** per file (or once per file change) and cache the result.

## Three modules

### [cache/ast_parser.py](../cache/ast_parser.py)

Walks each `.py` file with the stdlib `ast` module and extracts:

- module docstring (or `null` if missing)
- every class: name, docstring, line
- every function/method: name, signature with type hints, docstring, `documented` flag, line, and (transient) source body

The body is used only to seed the summarizer prompt and is stripped before the cache is saved.

### [cache/summarizer.py](../cache/summarizer.py)

Fills in missing descriptions. Per file, it sends **one batched prompt** containing:

- a "TASK A" block if the module has no docstring
- a "TASK B" block listing every undocumented function with its signature and body

The summarizer returns one JSON object with `file` and `functions` keys. Markdown fences and preamble are stripped defensively (`_safe_parse_json`). On any failure, name-based fallback descriptions are used so the cache build never fails.

**Already-documented code is never sent to the summarizer.** That's the cost saving.

### [cache/cache_manager.py](../cache/cache_manager.py)

Reads/writes `.review_cache.json` in the **target project's** root (not this tool's directory). For each file:

1. Compute SHA-256 of bytes.
2. If `cached_hash == current_hash` → reuse entry, skip work.
3. Else → re-parse and re-summarize that one file.

Files that no longer exist on disk get evicted. The cache is one JSON file per target project, so each project keeps its own.

## What the agent sees

`CacheManager.get_map()` renders the whole codebase as one block of text, used in the initial prompt:

```
api/routes.py — Toy HTTP request router demonstrating cross-file issue tracing.
  handle_login(request) | Pull credentials off the request and call the auth layer.
  handle_request(request) | Stub: dispatches HTTP methods to handlers.
auth.py — User authentication helpers backed by a local SQLite DB.
  login(username, password) | Authenticate a user and return a session dict, or None.
  _hash_password(raw) | Hashes a raw password with MD5 (insecure).
```

Compact, scannable, and good enough for the agent to decide which files are worth opening with `get_file`.

## Where the cache lives

Inside the target project: e.g. `examples/buggy_app/.review_cache.json`. Adding it to your project's `.gitignore` is recommended — the cache is reproducible from source.
