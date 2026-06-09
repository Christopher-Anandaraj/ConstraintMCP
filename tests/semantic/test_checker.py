"""End-to-end tests for SemanticChecker. Uses real embeddings."""

import pytest

from constraint_mcp.semantic.baseline import BaselineStore
from constraint_mcp.semantic.checker import SemanticChecker
from constraint_mcp.semantic.rules import (
    CouplingBanRule,
    DomainCoherenceRule,
    DriftDetectionRule,
    SemanticRuleSet,
)

from .conftest import AUTH_CODE, DB_CODE, HANDLER_CODE


@pytest.fixture
def checker(engine, tmp_path):
    rule_set = SemanticRuleSet(
        coherence_rules=[
            DomainCoherenceRule(
                path_glob="src/auth/",
                domain_description="authentication, authorization, JWT tokens, sessions, login, credentials, password",
                threshold=0.45,
            )
        ],
        coupling_rules=[
            CouplingBanRule(
                path_glob="src/api/",
                forbidden_description="SQL queries, database connections, ORM models, cursor, raw query, fetchall",
                threshold=0.58,
            )
        ],
        drift_rules=[DriftDetectionRule(path_glob="src/core/", baseline_mode="auto", max_drift=0.30)],
    )
    store = BaselineStore(tmp_path / "b.db")
    return SemanticChecker(rule_set, store, engine)


class TestNoRules:
    def test_path_without_rules_is_approved(self, checker):
        assert not checker.check("src/unrelated/x.py", AUTH_CODE).is_violation

    def test_empty_rule_set_always_approves(self, engine, tmp_path):
        chk = SemanticChecker(SemanticRuleSet(), BaselineStore(tmp_path / "b.db"), engine)
        assert not chk.check("src/api/x.py", DB_CODE).is_violation


class TestDomainCoherence:
    def test_relevant_code_approved(self, checker):
        assert not checker.check("src/auth/session.py", AUTH_CODE).is_violation

    def test_off_domain_code_violates(self, checker):
        r = checker.check("src/auth/weird.py", DB_CODE)
        assert r.is_violation
        assert r.rule_type.value == "domain_coherence"


class TestCouplingBan:
    def test_forbidden_concern_violates(self, checker):
        r = checker.check("src/api/orders.py", DB_CODE)
        assert r.is_violation
        assert r.rule_type.value == "coupling_ban"
        assert "SEMANTIC VIOLATION" in r.message

    def test_clean_handler_approved(self, checker):
        assert not checker.check("src/api/orders.py", HANDLER_CODE).is_violation


class TestDriftDetection:
    def test_first_write_seeds_baseline_and_passes(self, checker):
        r = checker.check("src/core/engine.py", AUTH_CODE)
        assert not r.is_violation
        assert checker.baseline_store.get("src/core/engine.py") is not None

    def test_similar_content_passes(self, checker):
        checker.check("src/core/engine.py", AUTH_CODE)  # seed
        r = checker.check("src/core/engine.py", AUTH_CODE + "\n# minor tweak\n")
        assert not r.is_violation

    def test_large_change_violates(self, checker):
        checker.check("src/core/engine.py", AUTH_CODE)  # seed
        r = checker.check("src/core/engine.py", DB_CODE)
        assert r.is_violation
        assert r.rule_type.value == "drift_detection"


class TestEdgeCasesAndReload:
    def test_empty_content_approved(self, checker):
        assert not checker.check("src/auth/x.py", "").is_violation

    def test_low_signal_content_approved(self, checker):
        assert not checker.check("src/auth/x.py", "x = 1").is_violation

    def test_reload_replaces_rules(self, checker):
        assert checker.check("src/api/orders.py", DB_CODE).is_violation
        checker.reload(SemanticRuleSet())
        assert not checker.check("src/api/orders.py", DB_CODE).is_violation

    def test_update_baseline_only_for_drift_paths(self, checker):
        checker.update_baseline("src/auth/session.py", AUTH_CODE)  # no drift rule here
        assert checker.baseline_store.get("src/auth/session.py") is None
