"""Tests for parsing the ## Semantic Constraints section of SPEC.md."""

from constraint_mcp.semantic.parser import parse_semantic_constraints

SPEC = '''# My Project

## Constraints

### Banned Imports
- No `requests` — use `httpx` only

## Semantic Constraints

### Domain Coherence
- `src/auth/` — must match domain: "authentication, JWT tokens, sessions, login"
  threshold: 0.35
- `src/payments/` — must match domain: "payments, billing, Stripe, invoices"
  threshold: 0.30

### Semantic Coupling Bans
- `src/api/` — must not contain: "SQL queries, database connections, ORM, cursor"
  threshold: 0.45
- `src/utils/` — must not contain: "user authentication, password hashing"

### Semantic Drift
- `src/core/` — baseline: auto, max-drift: 0.20
- `src/core/auth.py` — baseline: locked, max-drift: 0.15
- `src/legacy/` — baseline: auto

## Architecture Rules
- Files in `src/api/` must never import from `src/db/` directly
'''


class TestParseSemanticConstraints:
    def test_counts(self):
        rs = parse_semantic_constraints(SPEC)
        assert len(rs.coherence_rules) == 2
        assert len(rs.coupling_rules) == 2
        assert len(rs.drift_rules) == 3

    def test_coherence_fields(self):
        rs = parse_semantic_constraints(SPEC)
        auth = rs.coherence_rules[0]
        assert auth.path_glob == "src/auth/"
        assert "authentication" in auth.domain_description
        assert auth.threshold == 0.35
        assert rs.coherence_rules[1].threshold == 0.30

    def test_coupling_threshold_default(self):
        rs = parse_semantic_constraints(SPEC)
        assert rs.coupling_rules[0].threshold == 0.45
        assert rs.coupling_rules[1].threshold == 0.45  # default when omitted

    def test_drift_modes_and_defaults(self):
        rs = parse_semantic_constraints(SPEC)
        d_auto, d_locked, d_legacy = rs.drift_rules
        assert d_auto.baseline_mode == "auto" and d_auto.max_drift == 0.20
        assert d_locked.baseline_mode == "locked" and d_locked.max_drift == 0.15
        assert d_legacy.baseline_mode == "auto" and d_legacy.max_drift == 0.25  # default

    def test_no_semantic_section_is_backward_compatible(self):
        assert parse_semantic_constraints("## Constraints\n### Banned Imports\n- No `x`").is_empty
        assert parse_semantic_constraints("").is_empty

    def test_section_ends_at_next_h2(self):
        # Architecture bullet must not leak into any semantic rule.
        rs = parse_semantic_constraints(SPEC)
        all_globs = [r.path_glob for r in (*rs.coherence_rules, *rs.coupling_rules, *rs.drift_rules)]
        assert all("import" not in g for g in all_globs)
