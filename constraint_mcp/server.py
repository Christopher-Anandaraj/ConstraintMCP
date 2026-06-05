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


def _on_spec_reload(new_config: ConstraintConfig) -> None:
    global _config
    with _config_lock:
        _config = new_config


def _get_config() -> ConstraintConfig:
    with _config_lock:
        return _config


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
    violation report with the exact rule violated and a suggested fix.
    """
    config = _get_config()

    if config.is_empty:
        logger.info("Passthrough mode — no constraints loaded. Approving %s.", filepath)
        return {"status": "approved", "filepath": filepath}

    violations = run_all_checks(filepath, content, config)

    if not violations:
        logger.info("Approved write to %s.", filepath)
        return {"status": "approved", "filepath": filepath}

    first = violations[0]
    logger.warning("Blocked write to %s — %d violation(s).", filepath, len(violations))

    return {
        "status": "violation",
        "rule": first.rule,
        "filepath": filepath,
        "line": first.line,
        "fix": first.suggestion,
        "all_violations": [
            {"rule": v.rule, "line": v.line, "fix": v.suggestion} for v in violations
        ],
        "message": _violation_message(violations, filepath),
    }


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


def main() -> None:
    """Entry point: load spec, start watcher, serve MCP."""
    global _config

    spec_path = os.environ.get("CONSTRAINT_MCP_SPEC", "SPEC.md")
    _config = load_spec(spec_path)

    watcher = SpecWatcher(spec_path, _on_spec_reload)
    watcher.start()

    mcp.run()


if __name__ == "__main__":
    main()
