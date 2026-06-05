"""Tests for constraint_mcp.enforcer."""

import textwrap

import pytest

from constraint_mcp.enforcer import (
    check_architecture_rules,
    check_banned_imports,
    check_protected_files,
    run_all_checks,
)
from constraint_mcp.parser import ArchitectureRule, BannedImport, ConstraintConfig, ProtectedFile


class TestCheckBannedImports:
    def _rule(self, module: str, scope: str | None = None, reason: str = "") -> BannedImport:
        return BannedImport(module=module, reason=reason, scope=scope)

    def test_detects_direct_import(self):
        code = "import requests\n"
        violations = check_banned_imports("app.py", code, [self._rule("requests")])
        assert len(violations) == 1
        assert "requests" in violations[0].rule

    def test_detects_submodule_import(self):
        code = "from requests.auth import HTTPBasicAuth\n"
        violations = check_banned_imports("app.py", code, [self._rule("requests")])
        assert len(violations) == 1

    def test_no_violation_for_allowed_import(self):
        code = "import httpx\n"
        violations = check_banned_imports("app.py", code, [self._rule("requests")])
        assert violations == []

    def test_scope_restricts_enforcement(self):
        code = "import pickle\n"
        rule = self._rule("pickle", scope="src/")
        # File outside scope → no violation
        violations = check_banned_imports("tests/conftest.py", code, [rule])
        assert violations == []

    def test_scope_triggers_in_matching_path(self):
        code = "import pickle\n"
        rule = self._rule("pickle", scope="src/")
        violations = check_banned_imports("src/utils.py", code, [rule])
        assert len(violations) == 1

    def test_line_number_reported(self):
        code = textwrap.dedent("""\
            # header
            # another line
            import requests
        """)
        violations = check_banned_imports("app.py", code, [self._rule("requests")])
        assert violations[0].line == 3

    def test_multiple_banned_imports_all_caught(self):
        code = "import requests\nimport pickle\n"
        rules = [self._rule("requests"), self._rule("pickle")]
        violations = check_banned_imports("src/app.py", code, rules)
        assert len(violations) == 2

    def test_non_python_file_not_checked(self):
        config = ConstraintConfig(banned_imports=[self._rule("requests")])
        violations = run_all_checks("README.md", "import requests\n", config)
        assert violations == []


class TestCheckProtectedFiles:
    def test_exact_file_match(self):
        rules = [ProtectedFile(path="src/core/auth.py")]
        violations = check_protected_files("src/core/auth.py", rules)
        assert len(violations) == 1

    def test_no_violation_for_different_file(self):
        rules = [ProtectedFile(path="src/core/auth.py")]
        violations = check_protected_files("src/core/models.py", rules)
        assert violations == []

    def test_directory_blocks_nested_file(self):
        rules = [ProtectedFile(path="src/core/", is_directory=True)]
        violations = check_protected_files("src/core/secrets.py", rules)
        assert len(violations) == 1

    def test_directory_does_not_block_sibling(self):
        rules = [ProtectedFile(path="src/core/", is_directory=True)]
        violations = check_protected_files("src/api/users.py", rules)
        assert violations == []

    def test_leading_slash_normalised(self):
        rules = [ProtectedFile(path="src/core/auth.py")]
        violations = check_protected_files("/src/core/auth.py", rules)
        assert len(violations) == 1

    def test_violation_message_contains_path(self):
        rules = [ProtectedFile(path="config/prod.yaml")]
        violations = check_protected_files("config/prod.yaml", rules)
        assert "config/prod.yaml" in violations[0].rule


class TestCheckArchitectureRules:
    def _rule(self, source: str = "src/api/", banned: str = "src/db/") -> ArchitectureRule:
        return ArchitectureRule(
            source_layer=source,
            banned_layer=banned,
            description=f"Files in `{source}` must never import from `{banned}` directly",
        )

    def test_detects_layer_violation(self):
        code = "from src.db import session\n"
        violations = check_architecture_rules("src/api/users.py", code, [self._rule()])
        assert len(violations) == 1

    def test_no_violation_outside_source_layer(self):
        code = "from src.db import session\n"
        violations = check_architecture_rules("src/services/users.py", code, [self._rule()])
        assert violations == []

    def test_no_violation_for_clean_import(self):
        code = "from src.services import user_service\n"
        violations = check_architecture_rules("src/api/users.py", code, [self._rule()])
        assert violations == []

    def test_suggestion_mentions_layers(self):
        code = "from src.db import session\n"
        violations = check_architecture_rules("src/api/users.py", code, [self._rule()])
        assert "src/api/" in violations[0].suggestion


class TestRunAllChecks:
    def test_empty_config_approves_everything(self):
        config = ConstraintConfig()
        violations = run_all_checks("src/core/auth.py", "import requests\n", config)
        assert violations == []

    def test_multiple_violation_types_all_returned(self):
        config = ConstraintConfig(
            banned_imports=[BannedImport(module="requests", reason="use httpx")],
            protected_files=[ProtectedFile(path="src/core/auth.py")],
        )
        code = "import requests\n"
        violations = run_all_checks("src/core/auth.py", code, config)
        # Protected file + banned import
        assert len(violations) >= 2
