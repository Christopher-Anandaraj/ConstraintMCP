"""
Semantic (AST-based) enforcement demo.

Shows the difference between text/regex matching and real AST analysis:
- Comments, strings, and docstrings containing "import requests" → approved
- Actual import statements, even nested inside functions → blocked

Run:
    python example/demo_semantic.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from constraint_mcp.enforcer import run_all_checks
from constraint_mcp.parser import load_spec

SPEC_PATH = os.path.join(os.path.dirname(__file__), "SPEC.md")

RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

CASES = [
    # (label, filepath, content, expect_blocked)
    (
        "comment — text contains 'import requests'",
        "src/services/client.py",
        "# import requests  ← old dependency, replaced with httpx\nimport httpx\n",
        False,
    ),
    (
        "string literal — 'import requests' in a value",
        "src/utils/docs.py",
        "MIGRATION_NOTE = 'replaced import requests with httpx'\n",
        False,
    ),
    (
        "docstring — mentions requests in module docs",
        "src/api/routes.py",
        '"""Previously used import requests; now uses httpx."""\nimport httpx\n',
        False,
    ),
    (
        "variable named 'requests'",
        "src/api/routes.py",
        "requests = pending_requests()\nreturn requests\n",
        False,
    ),
    (
        "real import — import requests",
        "src/api/routes.py",
        "import requests\n\ndef fetch(url):\n    return requests.get(url).json()\n",
        True,
    ),
    (
        "aliased — import requests as r",
        "src/api/routes.py",
        "import requests as r\n\ndef fetch(url):\n    return r.get(url).json()\n",
        True,
    ),
    (
        "from-import — from requests import get",
        "src/api/routes.py",
        "from requests import get\n\ndef fetch(url):\n    return get(url).json()\n",
        True,
    ),
    (
        "nested — import requests inside a function",
        "src/api/routes.py",
        "def fetch(url):\n    import requests\n    return requests.get(url).json()\n",
        True,
    ),
]


def _show(label: str, filepath: str, content: str, config) -> None:
    print(f"\n  {DIM}{label}{RESET}")
    for line in content.strip().splitlines():
        print(f"    {CYAN}{line}{RESET}")
    time.sleep(0.5)

    violations = run_all_checks(filepath, content, config)

    if violations:
        print(f"  {RED}{BOLD}  ✗ BLOCKED{RESET}  {violations[0].rule}")
    else:
        print(f"  {GREEN}{BOLD}  ✓ APPROVED{RESET}  (not a real import — AST sees no import node)")
    time.sleep(0.9)


def main() -> None:
    config = load_spec(SPEC_PATH)

    print(f"\n{BOLD}constraint-mcp — AST semantic demo{RESET}")
    print(f"{DIM}Rule: no `requests` imports. Does text matching or real AST?{RESET}")

    print(f"\n{BOLD}── False positives a regex would produce (should all PASS) ──{RESET}")
    time.sleep(0.4)
    for label, fp, content, expect_blocked in CASES:
        if not expect_blocked:
            _show(label, fp, content, config)

    print(f"\n{BOLD}── Real violations (should all BLOCK) ──{RESET}")
    time.sleep(0.4)
    for label, fp, content, expect_blocked in CASES:
        if expect_blocked:
            _show(label, fp, content, config)

    print(f"\n{DIM}{'─' * 58}{RESET}")
    print(f"  {GREEN}4 false-positive candidates{RESET} → all approved (text, not code)")
    print(f"  {RED}4 real import forms{RESET}        → all blocked (AST catches them)\n")


if __name__ == "__main__":
    main()
