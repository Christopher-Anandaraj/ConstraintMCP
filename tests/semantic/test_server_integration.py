"""Tests for the semantic layer wired into the server's check_write tool."""

import pytest

import constraint_mcp.server as server_module
from constraint_mcp.parser import BannedImport, ConstraintConfig
from constraint_mcp.semantic.baseline import BaselineStore
from constraint_mcp.semantic.checker import SemanticChecker
from constraint_mcp.semantic.rules import CouplingBanRule, SemanticRuleSet

from .conftest import DB_CODE


@pytest.fixture
def wired_server(engine, tmp_path):
    """Configure the server module with a coupling-ban semantic rule, then restore."""
    saved_config = server_module._config
    saved_checker = server_module._semantic_checker

    rule_set = SemanticRuleSet(
        coupling_rules=[
            CouplingBanRule(
                path_glob="src/api/",
                forbidden_description="SQL queries, database connections, ORM, cursor, raw query, fetchall",
                threshold=0.58,
            )
        ]
    )
    store = BaselineStore(tmp_path / "b.db")

    def configure(strict: bool):
        server_module._config = ConstraintConfig()
        server_module._semantic_checker = SemanticChecker(rule_set, store, engine, strict=strict)

    yield configure

    server_module._config = saved_config
    server_module._semantic_checker = saved_checker


class TestSemanticInCheckWrite:
    def test_strict_blocks(self, wired_server):
        wired_server(strict=True)
        r = server_module.check_write("src/api/orders.py", DB_CODE)
        assert r["status"] == "violation"
        assert r["type"] == "semantic"
        assert r["rule_type"] == "coupling_ban"
        assert "SEMANTIC VIOLATION" in r["message"]

    def test_non_strict_approves_with_warnings(self, wired_server):
        wired_server(strict=False)
        r = server_module.check_write("src/api/orders.py", DB_CODE)
        assert r["status"] == "approved"
        assert len(r["semantic_warnings"]) == 1
        assert r["semantic_warnings"][0]["rule_type"] == "coupling_ban"

    def test_structural_violation_takes_precedence(self, wired_server):
        wired_server(strict=True)
        server_module._config = ConstraintConfig(
            banned_imports=[BannedImport(module="requests", reason="use httpx")]
        )
        r = server_module.check_write("src/api/orders.py", "import requests\n")
        assert r["status"] == "violation"
        assert r["type"] == "structural"

    def test_path_without_rule_is_approved(self, wired_server):
        wired_server(strict=True)
        r = server_module.check_write("src/other/x.py", DB_CODE)
        assert r["status"] == "approved"
        assert "semantic_warnings" not in r


class TestGetSemanticStatus:
    def test_reports_active_rules(self, wired_server):
        wired_server(strict=True)
        st = server_module.get_semantic_status()
        assert st["enabled"] is True
        assert len(st["semantic_rules"]["coupling_bans"]) == 1
        assert st["strict_mode"] is True

    def test_disabled_when_no_checker(self):
        saved = server_module._semantic_checker
        server_module._semantic_checker = None
        try:
            st = server_module.get_semantic_status()
            assert st["enabled"] is False
        finally:
            server_module._semantic_checker = saved
