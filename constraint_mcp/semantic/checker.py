"""SemanticChecker — orchestrates preprocessing, embedding, baselines, and rules."""

from __future__ import annotations

import logging

from .baseline import BaselineStore
from .embedder import EmbeddingEngine, embedding_engine
from .preprocessor import extract_semantic_text
from .rules import (
    CouplingBanRule,
    DomainCoherenceRule,
    DriftDetectionRule,
    SemanticCheckResult,
    SemanticRuleSet,
    SemanticRuleType,
)

logger = logging.getLogger(__name__)

_MIN_SIGNAL_CHARS = 20


def _coherence_message(filepath: str, rule: DomainCoherenceRule, score: float) -> str:
    return (
        "SEMANTIC VIOLATION — Domain Coherence\n\n"
        f"File:      {filepath}\n"
        f"Rule:      `{rule.path_glob}` must match domain: {rule.domain_description}\n"
        f"Score:     {score:.2f}  (threshold: ≥ {rule.threshold:.2f})\n"
        f"Detected:  This code is not semantically related enough to the domain "
        f"this directory is responsible for.\n\n"
        f"Fix:       Move this code to a directory that matches its purpose, or "
        f"keep `{rule.path_glob}` focused on: {rule.domain_description}."
    )


def _coupling_message(filepath: str, rule: CouplingBanRule, score: float) -> str:
    return (
        "SEMANTIC VIOLATION — Semantic Coupling Ban\n\n"
        f"File:      {filepath}\n"
        f"Rule:      `{rule.path_glob}` must not contain: {rule.forbidden_description}\n"
        f"Score:     {score:.2f}  (threshold: ≤ {rule.threshold:.2f})\n"
        f"Detected:  This code resembles concerns that are banned from this layer.\n\n"
        f"Fix:       Move that logic to the layer that owns it and call it through "
        f"a service boundary. `{rule.path_glob}` should not contain: "
        f"{rule.forbidden_description}."
    )


def _drift_message(filepath: str, rule: DriftDetectionRule, drift: float) -> str:
    return (
        "SEMANTIC VIOLATION — Semantic Drift\n\n"
        f"File:      {filepath}\n"
        f"Rule:      `{rule.path_glob}` baseline: {rule.baseline_mode}, max-drift: {rule.max_drift:.2f}\n"
        f"Drift:     {drift:.2f}  (allowed: ≤ {rule.max_drift:.2f})\n"
        f"Detected:  This change moves the file's meaning too far from its established baseline.\n\n"
        f"Fix:       Keep the change closer to the file's original responsibility, or "
        f"split the new behavior into a separate module."
    )


class SemanticChecker:
    """Runs all semantic checks for a ``(filepath, content)`` pair.

    Instantiated once per server process with a :class:`SemanticRuleSet`. The rule
    set can be hot-reloaded via :meth:`reload`.
    """

    def __init__(
        self,
        rule_set: SemanticRuleSet,
        baseline_store: BaselineStore,
        engine: EmbeddingEngine | None = None,
        strict: bool = False,
    ) -> None:
        self.rule_set = rule_set
        self.baseline_store = baseline_store
        self.engine = engine or embedding_engine
        self.strict = strict

    def reload(self, new_rule_set: SemanticRuleSet) -> None:
        """Hot-reload rules without restarting the server."""
        self.rule_set = new_rule_set

    def check(self, filepath: str, content: str) -> SemanticCheckResult:
        """Run every semantic rule matching ``filepath``; return the first violation.

        Rules are evaluated in order: coherence, then coupling, then drift. Empty
        content or too-little-signal content is always approved. A drift rule with
        no existing baseline approves the write and seeds the baseline.
        """
        if not content.strip():
            return SemanticCheckResult(is_violation=False)

        rules = self.rule_set.rules_for_path(filepath)
        if not rules:
            return SemanticCheckResult(is_violation=False)

        text = extract_semantic_text(filepath, content)
        if len(text.strip()) < _MIN_SIGNAL_CHARS:
            return SemanticCheckResult(is_violation=False)

        code_vec = self.engine.embed(text)

        # 1. Domain coherence
        for rule in (r for r in rules if isinstance(r, DomainCoherenceRule)):
            score = self.engine.similarity(code_vec, self.engine.embed(rule.domain_description))
            if score < rule.threshold:
                return SemanticCheckResult(
                    is_violation=True,
                    rule_type=SemanticRuleType.DOMAIN_COHERENCE,
                    rule_description=f"`{rule.path_glob}` must match domain: {rule.domain_description}",
                    similarity_score=score,
                    threshold=rule.threshold,
                    message=_coherence_message(filepath, rule, score),
                )

        # 2. Coupling bans
        for rule in (r for r in rules if isinstance(r, CouplingBanRule)):
            score = self.engine.similarity(code_vec, self.engine.embed(rule.forbidden_description))
            if score > rule.threshold:
                return SemanticCheckResult(
                    is_violation=True,
                    rule_type=SemanticRuleType.COUPLING_BAN,
                    rule_description=f"`{rule.path_glob}` must not contain: {rule.forbidden_description}",
                    similarity_score=score,
                    threshold=rule.threshold,
                    message=_coupling_message(filepath, rule, score),
                )

        # 3. Drift detection
        for rule in (r for r in rules if isinstance(r, DriftDetectionRule)):
            baseline = self.baseline_store.get(filepath)
            if baseline is None:
                # First write seeds the baseline and always passes.
                self.baseline_store.set(filepath, content, code_vec, rule.baseline_mode)
                continue
            drift = 1.0 - self.engine.similarity(code_vec, baseline)
            if drift > rule.max_drift:
                return SemanticCheckResult(
                    is_violation=True,
                    rule_type=SemanticRuleType.DRIFT_DETECTION,
                    rule_description=f"`{rule.path_glob}` drift exceeded max-drift {rule.max_drift:.2f}",
                    similarity_score=1.0 - drift,
                    threshold=rule.max_drift,
                    message=_drift_message(filepath, rule, drift),
                )

        return SemanticCheckResult(is_violation=False)

    def update_baseline(self, filepath: str, content: str) -> None:
        """Update baselines after a fully approved write (AST + semantic both pass).

        Only files covered by a :class:`DriftDetectionRule` are stored. Locked
        baselines that already exist are left untouched by the store.
        """
        if not content.strip():
            return
        drift_rules = [
            r for r in self.rule_set.rules_for_path(filepath) if isinstance(r, DriftDetectionRule)
        ]
        if not drift_rules:
            return
        text = extract_semantic_text(filepath, content)
        if len(text.strip()) < _MIN_SIGNAL_CHARS:
            return
        rule = drift_rules[0]
        self.baseline_store.set(filepath, content, self.engine.embed(text), rule.baseline_mode)
