"""
Demo script that intentionally triggers all three constraint types.

Run this to see constraint-mcp blocking violations in real time:

    python example/demo.py

Each scenario prints what check_write() returns for a proposed bad write.
"""

from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from constraint_mcp.enforcer import run_all_checks
from constraint_mcp.parser import load_spec

SPEC_PATH = os.path.join(os.path.dirname(__file__), "SPEC.md")

# ANSI colors
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"


def _header(scenario: str, title: str) -> None:
    print()
    print(f"{DIM}{'─' * 56}{RESET}")
    print(f"  {CYAN}{BOLD}{scenario}{RESET}  {title}")
    print(f"{DIM}{'─' * 56}{RESET}")
    time.sleep(0.3)


def _show(filepath: str, content: str, config) -> None:
    # Show the code being attempted
    print(f"\n{DIM}  attempting write → {filepath}{RESET}")
    for line in content.strip().splitlines():
        print(f"  {DIM}{line}{RESET}")
    print()
    time.sleep(0.4)

    violations = run_all_checks(filepath, content, config)

    if violations:
        print(f"  {RED}{BOLD}✗ BLOCKED{RESET}  {BOLD}{filepath}{RESET}")
        for v in violations:
            print(f"  {YELLOW}  rule {RESET}  {v.rule}")
            if v.line:
                print(f"  {YELLOW}  line {RESET}  {v.line}")
            print(f"  {YELLOW}  fix  {RESET}  {v.suggestion}")
    else:
        print(f"  {GREEN}{BOLD}✓ APPROVED{RESET}  {BOLD}{filepath}{RESET}")

    time.sleep(0.5)


def main() -> None:
    config = load_spec(SPEC_PATH)

    print(f"\n{BOLD}constraint-mcp demo{RESET} — {DIM}SPEC.md loaded, 3 rule types active{RESET}")

    _header("1/4", "Banned import: `requests`")
    _show("src/api/client.py", """\
import requests

def fetch(url):
    return requests.get(url).json()
""", config)

    _header("2/4", "Protected file: `src/core/auth.py`")
    _show("src/core/auth.py", "# overwrite attempt\n", config)

    _header("3/4", "Protected directory: `src/core/`")
    _show("src/core/secrets.py", "PASSWORD = 'hunter2'\n", config)

    _header("4a/4", "Architecture violation: src/api/ → src/db/")
    _show("src/api/users.py", """\
from src.db import session

def get_users():
    return session.query('SELECT * FROM users')
""", config)

    _header("4b/4", "Clean write — approved")
    _show("src/services/http_client.py", """\
import httpx

async def fetch(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        return (await client.get(url)).json()
""", config)

    print(f"\n{DIM}{'─' * 56}{RESET}\n")


if __name__ == "__main__":
    main()
