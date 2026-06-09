"""FastMCP server exposing constraint enforcement tools."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .enforcer import run_all_checks
from .parser import ConstraintConfig, load_spec
from .watcher import SpecWatcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s [constraint-mcp] %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("constraint-mcp")

# Shared mutable config protected by a lock so the watcher can hot-reload it.
_config_lock = threading.Lock()
_config: ConstraintConfig = ConstraintConfig()

# Optional semantic enforcement layer. Stays None unless main() wires it up, so
# direct tool calls in tests behave exactly as before the semantic layer existed.
_semantic_checker: "SemanticChecker | None" = None
_spec_path: str = "SPEC.md"


def _on_spec_reload(new_config: ConstraintConfig) -> None:
    global _config
    with _config_lock:
        _config = new_config
    # Hot-reload semantic rules from the same file (watcher only carries AST config).
    if _semantic_checker is not None:
        try:
            from .semantic.parser import parse_semantic_constraints

            text = Path(_spec_path).read_text(encoding="utf-8")
            _semantic_checker.reload(parse_semantic_constraints(text))
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to reload semantic rules: %s", exc)


def _get_config() -> ConstraintConfig:
    with _config_lock:
        return _config


def _get_semantic_checker() -> "SemanticChecker | None":
    return _semantic_checker


def _violation_message(violations: list, filepath: str) -> str:
    """Format violations into a context-window-friendly string for Claude."""
    lines = [
        "╔══════════════════════════════════════════════════════╗",
        "║          CONSTRAINT VIOLATION DETECTED               ║",
        "╚══════════════════════════════════════════════════════╝",
        f"File: {filepath}",
        f"Violations found: {len(violations)}",
        "",
    ]
    for i, v in enumerate(violations, 1):
        lines.append(f"[{i}] Rule:       {v.rule}")
        if v.line:
            lines.append(f"    Line:       {v.line}")
        lines.append(f"    Fix:        {v.suggestion}")
        lines.append("")
    lines.append("ACTION REQUIRED: Do NOT write this file. Fix the violations above first.")
    lines.append("Call check_write() again after making corrections.")
    return "\n".join(lines)


@mcp.tool()
def check_write(filepath: str, content: str) -> dict[str, Any]:
    """Check a proposed file write against all active constraints before allowing it.

    Must be called before writing any file. Returns an approval or a structured
    violation report with the exact rule violated and a suggested fix. Runs the
    structural (AST) checks first, then the optional semantic layer.
    """
    config = _get_config()
    semantic = _get_semantic_checker()
    semantic_active = semantic is not None and not semantic.rule_set.is_empty

    # 1. Structural (AST) checks — unchanged behavior.
    violations = [] if config.is_empty else run_all_checks(filepath, content, config)
    if violations:
        first = violations[0]
        logger.warning("Blocked write to %s — %d violation(s).", filepath, len(violations))
        return {
            "status": "violation",
            "type": "structural",
            "rule": first.rule,
            "filepath": filepath,
            "line": first.line,
            "fix": first.suggestion,
            "all_violations": [
                {"rule": v.rule, "line": v.line, "fix": v.suggestion} for v in violations
            ],
            "message": _violation_message(violations, filepath),
        }

    # Nothing to enforce at all → passthrough.
    if config.is_empty and not semantic_active:
        logger.info("Passthrough mode — no constraints loaded. Approving %s.", filepath)
        return {"status": "approved", "filepath": filepath}

    # 2. Semantic checks.
    semantic_result = semantic.check(filepath, content) if semantic_active else None

    if semantic_result is not None and semantic_result.is_violation and semantic.strict:
        logger.warning("Blocked write to %s — semantic violation (%s).",
                       filepath, semantic_result.rule_type.value)
        return {
            "status": "violation",
            "type": "semantic",
            "rule": semantic_result.rule_description,
            "filepath": filepath,
            "rule_type": semantic_result.rule_type.value,
            "score": round(semantic_result.similarity_score, 4),
            "threshold": semantic_result.threshold,
            "message": semantic_result.message,
        }

    # 3. Approved. Update drift baselines, attach non-strict warnings if any.
    if semantic_active:
        semantic.update_baseline(filepath, content)

    response: dict[str, Any] = {"status": "approved", "filepath": filepath}
    if semantic_result is not None and semantic_result.is_violation and not semantic.strict:
        response["semantic_warnings"] = [
            {
                "rule_type": semantic_result.rule_type.value,
                "rule": semantic_result.rule_description,
                "score": round(semantic_result.similarity_score, 4),
                "threshold": semantic_result.threshold,
                "message": semantic_result.message,
            }
        ]
        logger.info("Approved write to %s with %d semantic warning(s).", filepath, 1)
    else:
        logger.info("Approved write to %s.", filepath)
    return response


@mcp.tool()
def get_constraints() -> dict[str, Any]:
    """Return all active constraints parsed from SPEC.md.

    Call this at session start to load rules into your context window.
    """
    config = _get_config()

    if config.is_empty:
        return {
            "mode": "passthrough",
            "message": "No SPEC.md found — all writes are approved.",
            "banned_imports": [],
            "protected_files": [],
            "architecture_rules": [],
        }

    return {
        "mode": "enforcing",
        "banned_imports": [
            {"module": b.module, "scope": b.scope, "reason": b.reason}
            for b in config.banned_imports
        ],
        "protected_files": [
            {"path": p.path, "is_directory": p.is_directory}
            for p in config.protected_files
        ],
        "architecture_rules": [
            {
                "source_layer": r.source_layer,
                "banned_layer": r.banned_layer,
                "description": r.description,
            }
            for r in config.architecture_rules
        ],
    }


@mcp.tool()
def report_violation(rule: str, filepath: str, line: int) -> dict[str, Any]:
    """Log a constraint violation to constraint_violations.log.

    Use this to record violations that were caught and surfaced to the user.
    """
    log_path = Path("constraint_violations.log")
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = f"[{timestamp}] VIOLATION | file={filepath} | line={line} | rule={rule}\n"

    try:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(entry)
        logger.info("Violation logged to %s.", log_path)
        return {
            "status": "logged",
            "log_file": str(log_path.resolve()),
            "entry": entry.strip(),
        }
    except OSError as exc:
        logger.error("Could not write to %s: %s", log_path, exc)
        return {"status": "error", "message": str(exc)}


@mcp.tool()
def get_semantic_status() -> dict[str, Any]:
    """Return the semantic health of the codebase.

    Lists which semantic rules are active, which files have established drift
    baselines, and whether semantic violations block writes (strict mode). Call
    at session start to understand semantic rules before writing files.
    """
    semantic = _get_semantic_checker()
    if semantic is None:
        return {
            "enabled": False,
            "message": "Semantic layer is not active (no semantic rules or disabled).",
            "semantic_rules": {"coherence": [], "coupling_bans": [], "drift": []},
            "baselines": {"count": 0, "files": []},
            "strict_mode": False,
        }

    rs = semantic.rule_set
    return {
        "enabled": not rs.is_empty,
        "semantic_rules": {
            "coherence": [
                {"path_glob": r.path_glob, "domain": r.domain_description, "threshold": r.threshold}
                for r in rs.coherence_rules
            ],
            "coupling_bans": [
                {"path_glob": r.path_glob, "forbidden": r.forbidden_description, "threshold": r.threshold}
                for r in rs.coupling_rules
            ],
            "drift": [
                {"path_glob": r.path_glob, "mode": r.baseline_mode, "max_drift": r.max_drift}
                for r in rs.drift_rules
            ],
        },
        "baselines": {
            "count": semantic.baseline_store.count(),
            "files": semantic.baseline_store.files(),
        },
        "strict_mode": semantic.strict,
    }


def main() -> None:
    """Entry point: load spec, start watcher, wire semantic layer, serve MCP."""
    global _config, _semantic_checker, _spec_path

    spec_path = os.environ.get("CONSTRAINT_MCP_SPEC", "SPEC.md")
    _spec_path = spec_path
    _config = load_spec(spec_path)

    _semantic_checker = _build_semantic_checker(spec_path)

    watcher = SpecWatcher(spec_path, _on_spec_reload)
    watcher.start()

    mcp.run()


def _build_semantic_checker(spec_path: str) -> "SemanticChecker | None":
    """Construct the SemanticChecker from SPEC.md, or None if disabled/unavailable.

    Returns None when ``CONSTRAINT_MCP_SEMANTIC_DISABLED`` is truthy, when the
    spec has no semantic rules, or when the optional dependencies are missing —
    in every case the server falls back to structural-only enforcement.
    """
    if os.environ.get("CONSTRAINT_MCP_SEMANTIC_DISABLED", "false").lower() == "true":
        logger.info("Semantic layer disabled via CONSTRAINT_MCP_SEMANTIC_DISABLED.")
        return None

    try:
        from .semantic.baseline import BaselineStore
        from .semantic.checker import SemanticChecker
        from .semantic.embedder import embedding_engine
        from .semantic.parser import parse_semantic_constraints
    except Exception as exc:
        logger.warning("Semantic layer unavailable (%s) — structural enforcement only.", exc)
        return None

    try:
        text = Path(spec_path).read_text(encoding="utf-8") if Path(spec_path).exists() else ""
    except OSError:
        text = ""

    rule_set = parse_semantic_constraints(text)
    if rule_set.is_empty:
        logger.info("No semantic constraints found — structural enforcement only.")
        return None

    strict = os.environ.get("CONSTRAINT_MCP_SEMANTIC_STRICT", "false").lower() == "true"
    checker = SemanticChecker(
        rule_set=rule_set,
        baseline_store=BaselineStore(),
        engine=embedding_engine,
        strict=strict,
    )
    logger.info(
        "Semantic layer active: %d coherence, %d coupling, %d drift rules (strict=%s).",
        len(rule_set.coherence_rules), len(rule_set.coupling_rules),
        len(rule_set.drift_rules), strict,
    )
    return checker


if __name__ == "__main__":
    main()
