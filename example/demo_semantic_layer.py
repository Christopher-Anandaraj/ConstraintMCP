"""
Semantic (embedding-based) enforcement demo.

The AST layer checks structure: imports, filepaths, layers. This layer checks
*meaning* using local embeddings — catching code that's structurally fine but
semantically in the wrong place, or that has drifted from its baseline.

Run:
    python example/demo_semantic_layer.py
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
    DomainCoherenceRule,
    DriftDetectionRule,
    SemanticRuleSet,
)

RED, GREEN, YELLOW, CYAN, BOLD, DIM, RESET = (
    "\033[91m", "\033[92m", "\033[93m", "\033[96m", "\033[1m", "\033[2m", "\033[0m"
)

AUTH_CODE = '''"""User authentication and session management."""
import bcrypt, jwt
class SessionManager:
    """Handles login, credential verification, and JWT token issuance."""
    def authenticate(self, username, password):
        if bcrypt.checkpw(password, self.stored_hash):
            return jwt.encode({"uid": username})
'''
DB_CODE = '''"""Order persistence layer."""
class OrderRepository:
    """Executes raw SQL queries against the orders database table."""
    def get_pending(self, cursor):
        cursor.execute("SELECT * FROM orders WHERE status='pending'")
        return cursor.fetchall()
'''
HANDLER_CODE = '''"""HTTP request handler for the orders endpoint."""
class OrderHandler:
    """Parses the incoming HTTP request and returns a JSON response."""
    def handle(self, request):
        data = self.order_service.list_orders(request.user)
        return {"status": 200, "orders": data}
'''


def _header(title: str) -> None:
    print(f"\n{DIM}{'─' * 60}{RESET}")
    print(f"  {CYAN}{BOLD}{title}{RESET}")
    print(f"{DIM}{'─' * 60}{RESET}")
    time.sleep(0.5)


def _show(checker: SemanticChecker, label: str, filepath: str, code: str) -> None:
    print(f"\n  {DIM}{label}{RESET}")
    print(f"  {DIM}→ {filepath}{RESET}")
    time.sleep(0.4)
    result = checker.check(filepath, code)
    if result.is_violation:
        print(f"  {RED}{BOLD}✗ BLOCKED{RESET}  {result.rule_type.value}  "
              f"{DIM}(score {result.similarity_score:.2f} vs threshold {result.threshold:.2f}){RESET}")
    else:
        print(f"  {GREEN}{BOLD}✓ APPROVED{RESET}")
    time.sleep(0.9)


def main() -> None:
    engine = EmbeddingEngine()
    with tempfile.TemporaryDirectory() as d:
        store = BaselineStore(os.path.join(d, "baselines.db"))
        rules = SemanticRuleSet(
            coherence_rules=[DomainCoherenceRule(
                path_glob="src/auth/",
                domain_description="authentication, authorization, JWT tokens, sessions, login, credentials, password",
                threshold=0.45)],
            coupling_rules=[CouplingBanRule(
                path_glob="src/api/",
                forbidden_description="SQL queries, database connections, ORM models, cursor, raw query, fetchall",
                threshold=0.58)],
            drift_rules=[DriftDetectionRule(path_glob="src/core/", baseline_mode="auto", max_drift=0.30)],
        )
        checker = SemanticChecker(rules, store, engine, strict=True)

        print(f"\n{BOLD}constraint-mcp — semantic enforcement demo{RESET}")
        print(f"{DIM}Embedding-based meaning checks. No imports banned here — only meaning.{RESET}")

        _header("Domain Coherence — src/auth/ must be about authentication")
        _show(checker, "auth code (login, JWT, credentials)", "src/auth/session.py", AUTH_CODE)
        _show(checker, "database code — structurally fine, semantically wrong place", "src/auth/session.py", DB_CODE)

        _header("Coupling Ban — src/api/ must not contain database concerns")
        _show(checker, "clean HTTP handler (delegates to a service)", "src/api/orders.py", HANDLER_CODE)
        _show(checker, "raw SQL in the API layer", "src/api/orders.py", DB_CODE)

        _header("Drift — src/core/ must not stray far from its baseline")
        _show(checker, "first write — seeds the baseline", "src/core/engine.py", AUTH_CODE)
        _show(checker, "near-identical change", "src/core/engine.py", AUTH_CODE + "\n# small tweak\n")
        _show(checker, "wholesale rewrite into something unrelated", "src/core/engine.py", DB_CODE)

        print(f"\n{DIM}{'─' * 60}{RESET}")
        print(f"  {GREEN}Structurally valid code{RESET} can still be blocked when its {BOLD}meaning{RESET} is wrong.\n")


if __name__ == "__main__":
    main()
