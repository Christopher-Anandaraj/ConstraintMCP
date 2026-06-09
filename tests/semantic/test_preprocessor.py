"""Tests for semantic text extraction (preprocessor)."""

from constraint_mcp.semantic.preprocessor import extract_semantic_text, is_python_file

PY_SAMPLE = '''"""User authentication module."""
import bcrypt
from jwt import encode

class SessionManager:
    """Manages user login sessions and tokens."""
    def authenticate(self, user, pw):  # verify credentials
        # type: ignore
        hashed = bcrypt.checkpw(pw, self.stored)
        return encode({"uid": user.id})
'''


class TestPythonExtraction:
    def test_extracts_docstrings_names_comments_imports(self):
        out = extract_semantic_text("src/auth/session.py", PY_SAMPLE)
        assert "User authentication module." in out
        assert "SessionManager" in out
        assert "Manages user login sessions and tokens." in out
        assert "authenticate" in out
        assert "verify credentials" in out
        assert "bcrypt" in out
        assert "jwt" in out

    def test_strips_code_boilerplate(self):
        out = extract_semantic_text("src/auth/session.py", PY_SAMPLE)
        assert "bcrypt.checkpw" not in out
        assert "def " not in out
        assert "return encode" not in out

    def test_skips_tooling_directives(self):
        out = extract_semantic_text("src/auth/session.py", PY_SAMPLE)
        assert "type: ignore" not in out

    def test_imports_only_file(self):
        out = extract_semantic_text("a.py", "import os\nimport requests\n")
        assert "os" in out
        assert "requests" in out

    def test_pure_logic_falls_back_to_signal(self):
        out = extract_semantic_text("a.py", "x = compute()\ny = x + transform(x)\nreturn finalize(y)\n")
        assert len(out) > 0


class TestFallbackAndEdgeCases:
    def test_non_python_fallback(self):
        out = extract_semantic_text("src/app.ts", "const x = 1;\n\n\nfunction foo() { return 2; }\n")
        assert "const x = 1;" in out

    def test_empty_content_returns_empty(self):
        assert extract_semantic_text("a.py", "") == ""
        assert extract_semantic_text("a.py", "   \n  \t\n") == ""

    def test_output_is_capped(self):
        big = '"""' + ("word " * 2000) + '"""\n'
        out = extract_semantic_text("a.py", big)
        assert len(out) <= 2000

    def test_is_python_file(self):
        assert is_python_file("x.py")
        assert not is_python_file("x.ts")
        assert not is_python_file("x.go")
