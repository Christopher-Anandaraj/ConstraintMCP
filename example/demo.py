"""
Demo script that intentionally triggers all three constraint types.

Run this to see constraint-mcp blocking violations in real time:

    CONSTRAINT_MCP_SPEC=example/SPEC.md python example/demo.py

Each scenario prints what check_write() returns for a proposed bad write.
"""

from __future__ import annotations

import sys
import os

# Allow running from the repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from constraint_mcp.enforcer import run_all_checks
from constraint_mcp.parser import load_spec

SPEC_PATH = os.path.join(os.path.dirname(__file__), "SPEC.md")


def _header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def _show(filepath: str, content: str, config) -> None:
    violations = run_all_checks(filepath, content, config)
    if violations:
        print(f"BLOCKED  {filepath}")
        for v in violations:
            print(f"  Rule:  {v.rule}")
            print(f"  Line:  {v.line}")
            print(f"  Fix:   {v.suggestion}")
    else:
        print(f"APPROVED {filepath}")


def main() -> None:
    config = load_spec(SPEC_PATH)

    # ── Scenario 1: Banned import ────────────────────────────────────────────
    _header("SCENARIO 1 — Banned import: requests")
    bad_requests = """\
import requests

def fetch(url):
    return requests.get(url).json()
"""
    _show("src/api/client.py", bad_requests, config)

    # ── Scenario 2: Protected file ────────────────────────────────────────────
    _header("SCENARIO 2 — Protected file: src/core/auth.py")
    any_content = "# This would overwrite the protected auth module\n"
    _show("src/core/auth.py", any_content, config)

    # ── Scenario 3: Protected directory ──────────────────────────────────────
    _header("SCENARIO 3 — Protected directory: src/core/")
    _show("src/core/secrets.py", "PASSWORD = 'hunter2'\n", config)

    # ── Scenario 4: Architecture violation ───────────────────────────────────
    _header("SCENARIO 4 — Architecture violation: src/api/ → src/db/")
    bad_arch = """\
from src.db import session

def get_users():
    return session.query('SELECT * FROM users')
"""
    _show("src/api/users.py", bad_arch, config)

    # ── Scenario 5: Clean write (should be approved) ─────────────────────────
    _header("SCENARIO 5 — Clean write (should be approved)")
    good = """\
import httpx

async def fetch(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
"""
    _show("src/services/http_client.py", good, config)


if __name__ == "__main__":
    main()
