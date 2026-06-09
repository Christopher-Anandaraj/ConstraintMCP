"""Shared fixtures for semantic tests that use real embeddings.

The embedding model is loaded once per test session (it is comparatively slow to
construct) and reused across all embedding-based tests.
"""

import pytest

from constraint_mcp.semantic.embedder import EmbeddingEngine

# Realistic code samples with clear, separable semantics.
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


@pytest.fixture(scope="session")
def engine() -> EmbeddingEngine:
    return EmbeddingEngine()
