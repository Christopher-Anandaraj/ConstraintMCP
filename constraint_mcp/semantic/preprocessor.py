"""Extract the semantically meaningful parts of code before embedding.

Raw code carries a lot of noise (brackets, indentation, boilerplate) that
dilutes embeddings. For Python we walk the tree-sitter AST and pull out the
signal: docstrings, class/function names, comments, and import module names.
Non-Python files fall back to compressed raw text.
"""

from __future__ import annotations

import logging

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

logger = logging.getLogger(__name__)

_PY_LANGUAGE = Language(tspython.language())
_parser = Parser(_PY_LANGUAGE)

MAX_OUTPUT_CHARS = 2000
_MIN_DOC_STRING_LEN = 30


def is_python_file(filepath: str) -> bool:
    """True if the path looks like a Python source file."""
    return filepath.endswith(".py")


def _strip_quotes(text: str) -> str:
    """Remove surrounding string quotes/prefixes from a string literal node's text."""
    t = text.strip()
    for prefix in ('"""', "'''", '"', "'"):
        if t.startswith(prefix) and t.endswith(prefix) and len(t) >= 2 * len(prefix):
            return t[len(prefix):-len(prefix)].strip()
    # handle string prefixes like r"...", f"..."
    if len(t) > 1 and t[0] in "rRbBfFuU":
        return _strip_quotes(t[1:])
    return t


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_python(content: str) -> str:
    """Pull docstrings, names, comments, doc-like strings, and imports from Python."""
    source = content.encode("utf-8")
    tree = _parser.parse(source)
    parts: list[str] = []

    def first_docstring(body_node: Node) -> str | None:
        """Return the docstring text if the block's first statement is a string."""
        for child in body_node.named_children:
            if child.type == "expression_statement":
                inner = child.named_children[0] if child.named_children else None
                if inner is not None and inner.type == "string":
                    return _strip_quotes(_node_text(inner, source))
            return None  # first statement isn't a docstring
        return None

    def name_of(node: Node) -> str | None:
        ident = node.child_by_field_name("name")
        return _node_text(ident, source) if ident is not None else None

    def walk(node: Node) -> None:
        if node.type == "module":
            doc = first_docstring(node)
            if doc:
                parts.append(doc)
        elif node.type in ("function_definition", "class_definition"):
            nm = name_of(node)
            if nm:
                parts.append(nm)
            body = node.child_by_field_name("body")
            if body is not None:
                doc = first_docstring(body)
                if doc:
                    parts.append(doc)
        elif node.type == "comment":
            text = _node_text(node, source).lstrip("#").strip()
            # skip tooling directives like "type: ignore", "noqa", "pragma"
            lowered = text.lower()
            if text and not any(lowered.startswith(d) for d in ("type:", "noqa", "pragma", "pylint:")):
                parts.append(text)
        elif node.type == "string":
            # documentation-like string literals (long ones), not already captured as docstrings
            text = _strip_quotes(_node_text(node, source))
            if len(text) >= _MIN_DOC_STRING_LEN and parent_is_value(node):
                parts.append(text)
        elif node.type in ("import_statement", "import_from_statement"):
            for child in node.children:
                if child.type == "dotted_name":
                    parts.append(_node_text(child, source))

        for child in node.children:
            walk(child)

    def parent_is_value(node: Node) -> bool:
        # Avoid double-counting docstrings (handled above as expression_statement first child).
        p = node.parent
        if p is None:
            return True
        if p.type == "expression_statement" and p.parent is not None and p.parent.type in ("block", "module"):
            # could be a docstring position; only count if not the first statement
            block = p.parent
            first = block.named_children[0] if block.named_children else None
            return first is not p
        return True

    walk(tree.root_node)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for p in parts:
        key = p.strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)
    return "\n".join(deduped)


def _fallback_text(content: str) -> str:
    """For non-Python files: strip blank lines, compress whitespace, truncate."""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    joined = " ".join(lines)
    return joined[:1500]


def extract_semantic_text(filepath: str, content: str) -> str:
    """Return a cleaned text representation of code optimized for embedding.

    For Python: module/class/function docstrings, class & function names,
    significant comments, documentation-like string literals, and import module
    names. For other files: compressed raw content truncated to 1500 chars.
    Output is plain text, never code syntax, capped at ``MAX_OUTPUT_CHARS``.
    """
    if not content.strip():
        return ""

    if is_python_file(filepath):
        try:
            text = _extract_python(content)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Semantic preprocess failed for %s: %s — using fallback.", filepath, exc)
            text = _fallback_text(content)
        # If AST extraction yielded almost nothing (e.g. pure logic, no docs),
        # fall back so we still have a signal to embed.
        if len(text.strip()) < 20:
            text = _fallback_text(content)
    else:
        text = _fallback_text(content)

    return text[:MAX_OUTPUT_CHARS].strip()
