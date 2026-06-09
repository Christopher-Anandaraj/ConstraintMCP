"""Tests for semantic rule dataclasses and glob matching."""

from constraint_mcp.semantic.rules import (
    CouplingBanRule,
    DomainCoherenceRule,
    DriftDetectionRule,
    SemanticRuleSet,
    SemanticRuleType,
    _glob_matches,
)


class TestGlobMatching:
    def test_trailing_slash_matches_subtree(self):
        assert _glob_matches("src/auth/", "src/auth/utils.py")
        assert _glob_matches("src/auth/", "src/auth/deep/nested.py")

    def test_trailing_slash_does_not_match_sibling(self):
        assert not _glob_matches("src/auth/", "src/payments/utils.py")

    def test_double_star_glob(self):
        assert _glob_matches("src/auth/**", "src/auth/x.py")
        assert not _glob_matches("src/auth/**", "src/db/x.py")

    def test_exact_file_match(self):
        assert _glob_matches("src/core/auth.py", "src/core/auth.py")
        assert not _glob_matches("src/core/auth.py", "src/core/other.py")

    def test_leading_slash_normalized(self):
        assert _glob_matches("src/auth/", "/src/auth/x.py")

    def test_empty_glob_never_matches(self):
        assert not _glob_matches("", "anything.py")


class TestSemanticRuleSet:
    def _set(self):
        return SemanticRuleSet(
            coherence_rules=[DomainCoherenceRule(path_glob="src/auth/", domain_description="auth")],
            coupling_rules=[CouplingBanRule(path_glob="src/api/", forbidden_description="sql")],
            drift_rules=[DriftDetectionRule(path_glob="src/core/auth.py", baseline_mode="locked")],
        )

    def test_rules_for_path_filters_correctly(self):
        rs = self._set()
        assert len(rs.rules_for_path("src/auth/login.py")) == 1
        assert len(rs.rules_for_path("src/api/routes.py")) == 1
        assert len(rs.rules_for_path("src/core/auth.py")) == 1
        assert rs.rules_for_path("src/unrelated/x.py") == []

    def test_is_empty(self):
        assert SemanticRuleSet().is_empty
        assert not self._set().is_empty

    def test_rule_type_defaults(self):
        assert DomainCoherenceRule().type == SemanticRuleType.DOMAIN_COHERENCE
        assert CouplingBanRule().type == SemanticRuleType.COUPLING_BAN
        assert DriftDetectionRule().type == SemanticRuleType.DRIFT_DETECTION
        assert DomainCoherenceRule().threshold == 0.35
        assert CouplingBanRule().threshold == 0.45
        assert DriftDetectionRule().max_drift == 0.25
        assert DriftDetectionRule().baseline_mode == "auto"
