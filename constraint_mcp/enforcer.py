"""AST-based constraint enforcement using tree-sitter."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .parser import ArchitectureRule, BannedImport, ConstraintConfig, ProtectedFile

logger = logging.getLogger(__name__)

PY_LANGUAGE = Language(tspython.language())
_parser = Parser(PY_LANGUAGE)


@dataclass
class Violation:
    """A single constraint violation found during enforcement."""
    rule: str
    filepath: str
    line: int
    severity: str = "error"
    suggestion: str = ""


def _build_parser() -> Parser:
    return _parser


def _extract_imports(source: str) -> list[tuple[str, int]]:
    """Return list of (module_name, line_number) for all imports in source."""
    tree = _parser.parse(source.encode("utf-8"))
    imports: list[tuple[str, int]] = []

    def walk(node: Node) -> None:
        if node.type == "import_statement":
            # import foo, import foo.bar
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    name = child.text.decode("utf-8").split(" as ")[0].strip()
                    imports.append((name, node.start_point[0] + 1))
                    break
        elif node.type == "import_from_statement":
            # from foo import bar
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append((child.text.decode("utf-8"), node.start_point[0] + 1))
                    break
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return imports


def _module_matches(module: str, banned: str) -> bool:
    """Check if imported module matches a banned module name or prefix."""
    banned_clean = banned.rstrip(".*")
    return module == banned_clean or module.startswith(banned_clean + ".")


def check_banned_imports(
    filepath: str,
    content: str,
    rules: list[BannedImport],
) -> list[Violation]:
    """Check content for banned import violations."""
    violations: list[Violation] = []
    try:
        imports = _extract_imports(content)
    except Exception as exc:
        logger.warning("AST parse failed for %s: %s — skipping import checks.", filepath, exc)
        return violations

    for module, line in imports:
        for rule in rules:
            # Scope restriction: only enforce if filepath starts with scope
            if rule.scope and not filepath.startswith(rule.scope.lstrip("/")):
                continue
            if _module_matches(module, rule.module):
                reason_suffix = f" ({rule.reason})" if rule.reason else ""
                violations.append(Violation(
                    rule=f"Banned import: `{rule.module}`{reason_suffix}",
                    filepath=filepath,
                    line=line,
                    suggestion=rule.reason if rule.reason else f"Remove import of `{rule.module}`.",
                ))
    return violations


def check_protected_files(
    filepath: str,
    rules: list[ProtectedFile],
) -> list[Violation]:
    """Check if a filepath targets a protected file or directory."""
    violations: list[Violation] = []
    norm = filepath.lstrip("/")

    for rule in rules:
        rule_path = rule.path.lstrip("/")
        if rule.is_directory:
            if norm.startswith(rule_path) or norm.startswith(rule_path.rstrip("/")):
                violations.append(Violation(
                    rule=f"Protected directory: `{rule.path}` is locked",
                    filepath=filepath,
                    line=0,
                    suggestion=f"Do not write to files inside `{rule.path}`.",
                ))
        else:
            if norm == rule_path:
                violations.append(Violation(
                    rule=f"Protected file: `{rule.path}` is read-only",
                    filepath=filepath,
                    line=0,
                    suggestion=f"Do not modify `{rule.path}`.",
                ))
    return violations


def check_architecture_rules(
    filepath: str,
    content: str,
    rules: list[ArchitectureRule],
) -> list[Violation]:
    """Check that files in restricted layers don't import from banned layers."""
    violations: list[Violation] = []
    norm = filepath.lstrip("/")

    try:
        imports = _extract_imports(content)
    except Exception as exc:
        logger.warning("AST parse failed for %s: %s — skipping architecture checks.", filepath, exc)
        return violations

    for rule in rules:
        source = rule.source_layer.lstrip("/")
        banned = rule.banned_layer.lstrip("/")

        if not (norm.startswith(source) or norm.startswith(source.rstrip("/"))):
            continue

        # Convert layer path to importable module prefix (src/db/ → src.db)
        banned_module_prefix = banned.strip("/").replace("/", ".")

        for module, line in imports:
            if _module_matches(module, banned_module_prefix) or module.startswith(banned.strip("/")):
                violations.append(Violation(
                    rule=f"Architecture violation: {rule.description}",
                    filepath=filepath,
                    line=line,
                    suggestion=(
                        f"Files in `{rule.source_layer}` must not import from `{rule.banned_layer}`. "
                        f"Route through the appropriate service layer instead."
                    ),
                ))
    return violations


def run_all_checks(
    filepath: str,
    content: str,
    config: ConstraintConfig,
) -> list[Violation]:
    """Run all constraint checks and return every violation found."""
    violations: list[Violation] = []
    violations.extend(check_protected_files(filepath, config.protected_files))
    if filepath.endswith(".py"):
        violations.extend(check_banned_imports(filepath, content, config.banned_imports))
        violations.extend(check_architecture_rules(filepath, content, config.architecture_rules))
    return violations
