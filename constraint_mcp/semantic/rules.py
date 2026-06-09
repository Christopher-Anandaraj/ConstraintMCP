"""Semantic rule data types. Pure data — no logic beyond glob matching."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SemanticRuleType(Enum):
    """The three kinds of meaning-level constraint."""
    DOMAIN_COHERENCE = "domain_coherence"   # code must be semantically relevant to a domain
    COUPLING_BAN = "coupling_ban"           # code must NOT be semantically close to a domain
    DRIFT_DETECTION = "drift_detection"     # code must not drift too far from its baseline


@dataclass
class DomainCoherenceRule:
    """Enforce that files in a path glob are semantically relevant to a domain.

    SPEC.md syntax::

        - `src/auth/` — must match domain: "authentication, JWT, sessions, login"
          threshold: 0.35
    """
    path_glob: str = ""
    domain_description: str = ""
    threshold: float = 0.35   # minimum cosine similarity required (0.0–1.0)
    type: SemanticRuleType = SemanticRuleType.DOMAIN_COHERENCE


@dataclass
class CouplingBanRule:
    """Block writes where code is semantically too close to a forbidden domain.

    SPEC.md syntax::

        - `src/api/` — must not contain: "SQL, database connections, ORM, cursor"
          threshold: 0.45
    """
    path_glob: str = ""
    forbidden_description: str = ""
    threshold: float = 0.45   # maximum allowed cosine similarity (reject if ABOVE this)
    type: SemanticRuleType = SemanticRuleType.COUPLING_BAN


@dataclass
class DriftDetectionRule:
    """Block writes that drift a file's meaning too far from its baseline.

    SPEC.md syntax::

        - `src/core/` — baseline: auto, max-drift: 0.25
    """
    path_glob: str = ""
    max_drift: float = 0.25       # drift = 1.0 - cosine(new, baseline); violation if drift > max_drift
    baseline_mode: str = "auto"   # "auto" = tracks evolution; "locked" = frozen at first write
    type: SemanticRuleType = SemanticRuleType.DRIFT_DETECTION


# Union type used throughout the semantic subsystem.
SemanticRule = DomainCoherenceRule | CouplingBanRule | DriftDetectionRule


def _glob_matches(path_glob: str, filepath: str) -> bool:
    """Match a filepath against a SPEC.md path glob.

    A trailing-slash directory glob like ``src/auth/`` matches anything beneath it.
    A bare ``**`` glob is honored via fnmatch. An exact path matches only itself.
    """
    norm = filepath.lstrip("/")
    pat = path_glob.strip().lstrip("/")
    if not pat:
        return False
    if pat.endswith("/"):
        return norm.startswith(pat) or norm == pat.rstrip("/")
    # fnmatch treats ** like *, which is fine for our single-level use; also try
    # directory-prefix semantics for patterns ending in /** .
    if pat.endswith("/**"):
        prefix = pat[:-3]
        return norm.startswith(prefix + "/") or norm == prefix
    return fnmatch.fnmatch(norm, pat) or norm == pat


@dataclass
class SemanticRuleSet:
    """Container for all parsed semantic rules."""
    coherence_rules: list[DomainCoherenceRule] = field(default_factory=list)
    coupling_rules: list[CouplingBanRule] = field(default_factory=list)
    drift_rules: list[DriftDetectionRule] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.coherence_rules or self.coupling_rules or self.drift_rules)

    def rules_for_path(self, filepath: str) -> list[SemanticRule]:
        """Return every rule whose path glob matches ``filepath``."""
        matched: list[SemanticRule] = []
        for rule in (*self.coherence_rules, *self.coupling_rules, *self.drift_rules):
            if _glob_matches(rule.path_glob, filepath):
                matched.append(rule)
        return matched


@dataclass
class SemanticCheckResult:
    """Output of ``SemanticChecker.check()``. Mirrors the AST checker's shape."""
    is_violation: bool
    rule_type: Optional[SemanticRuleType] = None
    rule_description: str = ""      # human-readable rule that was violated
    similarity_score: float = 0.0   # actual cosine similarity computed
    threshold: float = 0.0          # threshold that was applied
    message: str = ""               # formatted message for LLM context injection
