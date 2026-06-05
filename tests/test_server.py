"""Tests for constraint_mcp.server tool logic (without running the MCP server)."""

import textwrap
from unittest.mock import patch

import pytest

from constraint_mcp.parser import BannedImport, ConstraintConfig, ProtectedFile


# We import the tool functions directly so we don't need a live MCP server.
import constraint_mcp.server as server_module


def _set_config(config: ConstraintConfig) -> None:
    """Directly set the module-level config for testing."""
    with server_module._config_lock:
        server_module._config = config


class TestCheckWriteTool:
    def test_approves_when_no_spec(self):
        _set_config(ConstraintConfig())
        result = server_module.check_write("src/utils.py", "x = 1\n")
        assert result["status"] == "approved"
        assert result["filepath"] == "src/utils.py"

    def test_blocks_banned_import(self):
        config = ConstraintConfig(
            banned_imports=[BannedImport(module="requests", reason="use httpx")]
        )
        _set_config(config)
        result = server_module.check_write("src/client.py", "import requests\n")
        assert result["status"] == "violation"
        assert "requests" in result["rule"]
        assert result["filepath"] == "src/client.py"

    def test_violation_includes_message_field(self):
        config = ConstraintConfig(
            banned_imports=[BannedImport(module="requests", reason="use httpx")]
        )
        _set_config(config)
        result = server_module.check_write("src/client.py", "import requests\n")
        assert "CONSTRAINT VIOLATION" in result["message"]

    def test_blocks_protected_file(self):
        config = ConstraintConfig(
            protected_files=[ProtectedFile(path="src/core/auth.py")]
        )
        _set_config(config)
        result = server_module.check_write("src/core/auth.py", "# overwrite\n")
        assert result["status"] == "violation"

    def test_violation_contains_all_violations_list(self):
        config = ConstraintConfig(
            banned_imports=[
                BannedImport(module="requests", reason="use httpx"),
                BannedImport(module="pickle", reason=""),
            ]
        )
        _set_config(config)
        code = "import requests\nimport pickle\n"
        result = server_module.check_write("src/app.py", code)
        assert result["status"] == "violation"
        assert len(result["all_violations"]) >= 2


class TestGetConstraintsTool:
    def test_passthrough_mode_when_empty(self):
        _set_config(ConstraintConfig())
        result = server_module.get_constraints()
        assert result["mode"] == "passthrough"

    def test_enforcing_mode_with_rules(self):
        config = ConstraintConfig(
            banned_imports=[BannedImport(module="requests", reason="use httpx")]
        )
        _set_config(config)
        result = server_module.get_constraints()
        assert result["mode"] == "enforcing"
        assert len(result["banned_imports"]) == 1
        assert result["banned_imports"][0]["module"] == "requests"


class TestReportViolationTool:
    def test_logs_to_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = server_module.report_violation(
            rule="Banned import: `requests`",
            filepath="src/client.py",
            line=3,
        )
        assert result["status"] == "logged"
        log_file = tmp_path / "constraint_violations.log"
        assert log_file.exists()
        contents = log_file.read_text()
        assert "requests" in contents
        assert "src/client.py" in contents

    def test_log_entry_contains_line_number(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        server_module.report_violation(
            rule="Banned import: `pickle`",
            filepath="src/utils.py",
            line=7,
        )
        log_file = tmp_path / "constraint_violations.log"
        assert "line=7" in log_file.read_text()
