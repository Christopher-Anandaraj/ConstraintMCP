"""Tests for constraint_mcp.parser."""

import textwrap
from pathlib import Path

import pytest

from constraint_mcp.parser import (
    ConstraintConfig,
    load_spec,
    _parse_banned_imports,
    _parse_protected_files,
    _parse_architecture_rules,
)


SAMPLE_SPEC = textwrap.dedent("""
    ## Constraints

    ### Banned Imports
    - No `requests` — use `httpx` only
    - No `pickle` anywhere in `src/`
    - No `os.system` — use `subprocess` only

    ### Protected Files
    - `src/core/auth.py` is read-only
    - `config/prod.yaml` must never be modified
    - `src/core/` directory is locked

    ### Architecture Rules
    - Files in `src/api/` must never import from `src/db/` directly
    - Files in `src/api/` must never import from `src/models/` directly
""")


class TestParseBannedImports:
    def test_parses_module_name(self):
        rules = _parse_banned_imports("- No `requests` — use `httpx` only")
        assert len(rules) == 1
        assert rules[0].module == "requests"

    def test_parses_reason(self):
        rules = _parse_banned_imports("- No `requests` — use `httpx` only")
        assert "httpx" in rules[0].reason

    def test_parses_scope(self):
        rules = _parse_banned_imports("- No `pickle` anywhere in `src/`")
        assert rules[0].module == "pickle"
        assert rules[0].scope == "src/"

    def test_multiple_rules(self):
        section = textwrap.dedent("""
            - No `requests` — use `httpx` only
            - No `pickle` anywhere in `src/`
            - No `os.system` — use `subprocess` only
        """)
        rules = _parse_banned_imports(section)
        assert len(rules) == 3

    def test_no_scope_when_absent(self):
        rules = _parse_banned_imports("- No `requests` — use `httpx` only")
        assert rules[0].scope is None


class TestParseProtectedFiles:
    def test_exact_file(self):
        rules = _parse_protected_files("- `src/core/auth.py` is read-only")
        assert len(rules) == 1
        assert rules[0].path == "src/core/auth.py"
        assert not rules[0].is_directory

    def test_must_never_be_modified(self):
        rules = _parse_protected_files("- `config/prod.yaml` must never be modified")
        assert rules[0].path == "config/prod.yaml"

    def test_directory_locked(self):
        rules = _parse_protected_files("- `src/core/` directory is locked")
        assert rules[0].is_directory is True

    def test_multiple_protected(self):
        section = textwrap.dedent("""
            - `src/core/auth.py` is read-only
            - `config/prod.yaml` must never be modified
            - `src/core/` directory is locked
        """)
        rules = _parse_protected_files(section)
        assert len(rules) == 3


class TestParseArchitectureRules:
    def test_source_and_banned_layers(self):
        rules = _parse_architecture_rules(
            "- Files in `src/api/` must never import from `src/db/` directly"
        )
        assert len(rules) == 1
        assert rules[0].source_layer == "src/api/"
        assert rules[0].banned_layer == "src/db/"

    def test_multiple_rules(self):
        section = textwrap.dedent("""
            - Files in `src/api/` must never import from `src/db/` directly
            - Files in `src/api/` must never import from `src/models/` directly
        """)
        rules = _parse_architecture_rules(section)
        assert len(rules) == 2

    def test_description_captured(self):
        rules = _parse_architecture_rules(
            "- Files in `src/api/` must never import from `src/db/` directly"
        )
        assert "src/api/" in rules[0].description


class TestLoadSpec:
    def test_passthrough_when_missing(self, tmp_path):
        config = load_spec(tmp_path / "nonexistent.md")
        assert config.is_empty

    def test_full_spec_loads(self, tmp_path):
        spec_file = tmp_path / "SPEC.md"
        spec_file.write_text(SAMPLE_SPEC)
        config = load_spec(spec_file)
        assert len(config.banned_imports) == 3
        assert len(config.protected_files) == 3
        assert len(config.architecture_rules) == 2

    def test_empty_spec_gives_empty_config(self, tmp_path):
        spec_file = tmp_path / "SPEC.md"
        spec_file.write_text("# Nothing here\n")
        config = load_spec(spec_file)
        assert config.is_empty
