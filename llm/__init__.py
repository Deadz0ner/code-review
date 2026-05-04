"""LLM provider abstraction.

Two roles are supported:
  - summarizer: cheap, one-shot text completion used by the cache layer.
  - reviewer: capable model used by the PydanticAI agent loop with tool use.
"""
