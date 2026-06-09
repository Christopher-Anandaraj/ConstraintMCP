"""Semantic (embedding-based) enforcement layer for constraint-mcp.

This subsystem runs alongside the AST checks in :mod:`constraint_mcp.enforcer`.
Where AST enforcement handles *structure* (imports, filepaths, layer boundaries),
the semantic layer handles *meaning* via embedding similarity:

- Domain coherence — code in a path must be semantically relevant to a domain.
- Semantic coupling bans — code in a path must NOT resemble a forbidden domain.
- Drift detection — a file's meaning must not drift far from its baseline.

The entire layer is optional and backward-compatible: a SPEC.md with no
``## Semantic Constraints`` section produces an empty rule set and the server
behaves exactly as before.
"""

from __future__ import annotations

__all__ = [
    "SemanticRuleType",
    "DomainCoherenceRule",
    "CouplingBanRule",
    "DriftDetectionRule",
    "SemanticRule",
    "SemanticRuleSet",
    "SemanticCheckResult",
]

from .rules import (
    CouplingBanRule,
    DomainCoherenceRule,
    DriftDetectionRule,
    SemanticCheckResult,
    SemanticRule,
    SemanticRuleSet,
    SemanticRuleType,
)
