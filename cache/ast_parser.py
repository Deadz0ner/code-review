"""Extract structural metadata from a Python source file using the stdlib `ast` module.

Returned shape per file:
    {
        "description": Optional[str],   # module docstring, or None to be filled by summarizer
        "classes": [{"name", "docstring", "documented", "line"}],
        "functions": [{"name", "signature", "docstring", "documented", "line", "body"}],
        "parse_error": bool,
    }

The `body` field is a transient string used by the summarizer; cache_manager strips
it before persisting.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Union

FuncNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]

_MAX_BODY_LINES = 60


def _format_arg(arg: ast.arg) -> str:
    """Render one argument as `name` or `name: Type`."""
    if arg.annotation is not None:
        return f"{arg.arg}: {ast.unparse(arg.annotation)}"
    return arg.arg


def _format_signature(node: FuncNode) -> str:
    """Render a function signature including type hints and return type."""
    args: List[str] = []
    posonly = getattr(node.args, "posonlyargs", []) or []
    args.extend(_format_arg(a) for a in posonly)
    if posonly:
        args.append("/")
    args.extend(_format_arg(a) for a in node.args.args)
    if node.args.vararg:
        args.append(f"*{node.args.vararg.arg}")
    elif node.args.kwonlyargs:
        args.append("*")
    args.extend(_format_arg(a) for a in node.args.kwonlyargs)
    if node.args.kwarg:
        args.append(f"**{node.args.kwarg.arg}")

    sig = f"{node.name}({', '.join(args)})"
    if node.returns is not None:
        sig += f" -> {ast.unparse(node.returns)}"
    return sig


def _function_body(source_lines: List[str], node: FuncNode) -> str:
    """Slice the function's source text from the file (truncated to keep prompts cheap)."""
    start = node.lineno - 1
    end = node.end_lineno or node.lineno
    body = source_lines[start:end]
    if len(body) > _MAX_BODY_LINES:
        body = body[:_MAX_BODY_LINES] + ["    # ... (truncated for summarizer)"]
    return "\n".join(body)


def _build_function_entry(
    node: FuncNode,
    source_lines: List[str],
    class_prefix: str = "",
) -> Dict[str, Any]:
    """Build a single function dict (works for module functions and class methods)."""
    doc = ast.get_docstring(node)
    name = f"{class_prefix}{node.name}" if class_prefix else node.name
    sig = _format_signature(node)
    if class_prefix:
        sig = f"{class_prefix}{sig}"
    return {
        "name": name,
        "signature": sig,
        "docstring": doc,
        "documented": doc is not None,
        "line": node.lineno,
        "body": _function_body(source_lines, node),
    }


def parse_file(path: Path) -> Dict[str, Any]:
    """Parse a single .py file and return its structural summary.

    Args:
        path: filesystem path to a Python source file.

    Returns:
        A dict with keys: description, classes, functions, parse_error.
        On a SyntaxError the dict has parse_error=True and empty class/function lists.
    """
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return {
            "description": None,
            "classes": [],
            "functions": [],
            "parse_error": True,
        }

    source_lines = source.splitlines()
    module_doc = ast.get_docstring(tree)

    classes: List[Dict[str, Any]] = []
    functions: List[Dict[str, Any]] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            cls_doc = ast.get_docstring(node)
            classes.append({
                "name": node.name,
                "docstring": cls_doc,
                "documented": cls_doc is not None,
                "line": node.lineno,
            })
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(
                        _build_function_entry(sub, source_lines, class_prefix=f"{node.name}.")
                    )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_build_function_entry(node, source_lines))

    return {
        "description": module_doc,
        "classes": classes,
        "functions": functions,
        "parse_error": False,
    }
