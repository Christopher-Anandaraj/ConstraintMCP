"""
constraint-mcp v2 hero demo — the CLAUDE.md vs. constraint-mcp contrast.

Two scenes. Each runs the SAME task twice: once with only a CLAUDE.md soft rule
(ignored — bad code lands), once with constraint-mcp (blocked at the gate, agent
self-corrects). All violation scores are produced by the real SemanticChecker.

Run:
    python example/demo_v2.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from constraint_mcp.semantic.baseline import BaselineStore
from constraint_mcp.semantic.checker import SemanticChecker
from constraint_mcp.semantic.embedder import EmbeddingEngine
from constraint_mcp.semantic.rules import (
    CouplingBanRule,
    DriftDetectionRule,
    SemanticRuleSet,
)

RED, GREEN, YELLOW, CYAN, BLUE, BOLD, DIM, RESET = (
    "\033[91m", "\033[92m", "\033[93m", "\033[96m", "\033[94m", "\033[1m", "\033[2m", "\033[0m"
)

SQL_IN_API = '''"""Orders API endpoint."""
class OrdersEndpoint:
    """Opens a database cursor and runs a raw SQL query on the orders table."""
    def list_pending(self, cursor):
        cursor.execute("SELECT * FROM orders WHERE status='pending'")
        return cursor.fetchall()
'''
CLEAN_API = '''"""Orders API endpoint."""
class OrdersEndpoint:
    """Validates the HTTP request and returns a JSON list of pending orders."""
    def list_pending(self, request):
        return {"orders": self.orders_service.pending(request.user)}
'''
SQL_IN_DB = '''"""Order persistence."""
class OrderRepository:
    """Raw SQL access to the orders table."""
    def pending(self, cursor):
        cursor.execute("SELECT * FROM orders WHERE status='pending'")
        return cursor.fetchall()
'''
AUTH_BASELINE = '''"""Core authentication."""
class Authenticator:
    """Verifies user credentials and issues session tokens."""
    def login(self, username, password):
        if self.verify_password(username, password):
            return self.issue_session_token(username)
'''
AUTH_DRIFTED = '''"""Core authentication."""
class Authenticator:
    """Charges the customer card and creates a Stripe subscription invoice."""
    def login(self, username, password):
        invoice = self.stripe.create_invoice(username, amount=4999)
        return self.stripe.charge(invoice, self.card_on_file(username))
'''


def _t(s: float) -> None:
    time.sleep(s)


def _type(text: str, color: str = "", delay: float = 0.0) -> None:
    print(f"{color}{text}{RESET}")
    _t(delay)


def _code(code: str, color: str = DIM) -> None:
    for line in code.strip().splitlines():
        print(f"      {color}{line}{RESET}")
    _t(0.5)


def scene_header(n: str, title: str) -> None:
    print()
    print(f"{BLUE}{BOLD}━━━ SCENE {n}: {title} ━━━{RESET}")
    _t(0.7)


def main() -> None:
    engine = EmbeddingEngine()
    with tempfile.TemporaryDirectory() as d:
        store = BaselineStore(os.path.join(d, "b.db"))
        rules = SemanticRuleSet(
            coupling_rules=[CouplingBanRule(
                path_glob="src/api/",
                forbidden_description="SQL queries, database connections, ORM models, cursor, raw query, fetchall",
                threshold=0.60)],
            drift_rules=[DriftDetectionRule(path_glob="src/core/", baseline_mode="locked", max_drift=0.22)],
        )
        checker = SemanticChecker(rules, store, engine, strict=True)

        print(f"{BOLD}constraint-mcp v2{RESET}  {DIM}— semantic enforcement for AI coding agents{RESET}")
        _t(0.8)

        # ───────────────────────── SCENE 1 ─────────────────────────
        scene_header("1", "Coupling ban — keep SQL out of the API layer")
        _type('Task: "Add an endpoint that lists pending orders."', DIM, 0.6)

        _type(f"\n{YELLOW}▌ With just CLAUDE.md{RESET}  (soft rule: \"src/api/ must not contain SQL\")", "", 0.5)
        _type("  agent writes src/api/orders.py", DIM)
        _code(SQL_IN_API)
        _type(f"  {GREEN}✓ file written{RESET}  {RED}← the rule was a suggestion. SQL is now in your API layer.{RESET}", "", 1.2)

        _type(f"\n{CYAN}▌ With constraint-mcp{RESET}  (same task, same model)", "", 0.5)
        _type("  agent calls check_write(\"src/api/orders.py\", ...)", DIM)
        r = checker.check("src/api/orders.py", SQL_IN_API)
        _type(f"  {RED}{BOLD}✗ BLOCKED{RESET}  coupling_ban   "
              f"{DIM}score {r.similarity_score:.2f}  (threshold ≤ {r.threshold:.2f}){RESET}", "", 0.3)
        _type(f"     {RED}detected database concerns in the API layer{RESET}", "", 1.0)
        _type("  agent self-corrects → moves the query to src/db/orders.py", DIM, 0.4)
        _code(SQL_IN_DB)
        r2 = checker.check("src/db/orders.py", SQL_IN_DB)
        r3 = checker.check("src/api/orders.py", CLEAN_API)
        _type(f"  {GREEN}✓ check_write(src/db/orders.py) → approved{RESET}", "", 0.3)
        _type(f"  {GREEN}✓ check_write(src/api/orders.py, service call) → approved{RESET}", "", 1.2)

        # ───────────────────────── SCENE 2 ─────────────────────────
        scene_header("2", "Drift detection — keep src/core/auth.py in scope")
        # seed the locked baseline with the real auth code
        checker.check("src/core/auth.py", AUTH_BASELINE)
        _type("baseline locked: src/core/auth.py is about authentication", DIM, 0.6)
        _type('Task: "Refactor the login method."', DIM, 0.6)

        _type(f"\n{YELLOW}▌ With just CLAUDE.md{RESET}  (soft rule: \"src/core/ stays in scope\")", "", 0.5)
        _type("  mid-refactor, the agent rewrites login() into billing logic", DIM)
        _code(AUTH_DRIFTED)
        _type(f"  {GREEN}✓ file written{RESET}  {RED}← auth.py now charges credit cards. Nothing stopped it.{RESET}", "", 1.2)

        _type(f"\n{CYAN}▌ With constraint-mcp{RESET}", "", 0.5)
        _type("  agent calls check_write(\"src/core/auth.py\", ...)", DIM)
        rd = checker.check("src/core/auth.py", AUTH_DRIFTED)
        drift = 1.0 - rd.similarity_score
        _type(f"  {RED}{BOLD}✗ BLOCKED{RESET}  drift_detection   "
              f"{DIM}drift {drift:.2f}  (allowed ≤ {rd.threshold:.2f}){RESET}", "", 0.3)
        _type(f"     {RED}this change moves auth.py far from its locked baseline{RESET}", "", 1.0)
        _type("  agent reverts → keeps payment logic out of core/auth.py", DIM, 1.0)

        print()
        print(f"{DIM}{'─' * 64}{RESET}")
        _type(f"  CLAUDE.md {BOLD}asks{RESET}. constraint-mcp {BOLD}enforces{RESET} — "
              f"at the code level, before the write.", "", 0.2)


if __name__ == "__main__":
    main()
