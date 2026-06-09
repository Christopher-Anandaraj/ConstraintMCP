"""Parse the ``## Semantic Constraints`` section of a SPEC.md string.

Kept separate from :mod:`constraint_mcp.parser` (which handles the AST rules) so
the existing parser is untouched. ``server.py`` calls both and merges results.
A SPEC.md without a ``## Semantic Constraints`` section yields an empty rule set,
keeping repos that don't use semantic rules fully backward-compatible.
"""

from __future__ import annotations

import logging
import re

from .rules import (
    CouplingBanRule,
    DomainCoherenceRule,
    DriftDetectionRule,
    SemanticRuleSet,
)

logger = logging.getLogger(__name__)

# `path` — must match domain: "description"    (threshold parsed from following line)
_COHERENCE_RE = re.compile(
    r"-\s+`([^`]+)`\s*[—–-]\s*must\s+match\s+domain:\s*\"([^\"]+)\"",
    re.IGNORECASE,
)
# `path` — must not contain: "description"
_COUPLING_RE = re.compile(
    r"-\s+`([^`]+)`\s*[—–-]\s*must\s+not\s+contain:\s*\"([^\"]+)\"",
    re.IGNORECASE,
)
# `path` — baseline: auto, max-drift: 0.20
_DRIFT_RE = re.compile(
    r"-\s+`([^`]+)`\s*[—–-]\s*baseline:\s*(auto|locked)"
    r"(?:\s*,\s*max-drift:\s*([0-9]*\.?[0-9]+))?",
    re.IGNORECASE,
)
_THRESHOLD_RE = re.compile(r"threshold:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


def _extract_section(spec_md: str, header: str) -> str | None:
    """Return the body of a ``## header`` section, or None if absent.

    The section ends at the next ``## `` header or end of file. Header match is
    case-insensitive.
    """
    lines = spec_md.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        if h2:
            if capturing:
                break  # next H2 ends the section
            if h2.group(1).strip().lower() == header.lower():
                capturing = True
                continue
        elif capturing:
            out.append(line)
    if not capturing:
        return None
    return "\n".join(out)


def _split_subsections(section: str) -> dict[str, list[str]]:
    """Map H3 subsection name (lowercased) → list of its body lines."""
    subs: dict[str, list[str]] = {}
    current: str | None = None
    for line in section.splitlines():
        h3 = re.match(r"^###\s+(.+?)\s*$", line)
        if h3:
            current = h3.group(1).strip().lower()
            subs[current] = []
        elif current is not None:
            subs[current].append(line)
    return subs


def _threshold_on_next_lines(lines: list[str], start: int, default: float) -> float:
    """Look at the line(s) after a bullet for a ``threshold:`` value."""
    for j in range(start + 1, min(start + 3, len(lines))):
        nxt = lines[j].strip()
        if nxt.startswith("-"):
            break  # next bullet; no threshold attached
        m = _THRESHOLD_RE.search(nxt)
        if m:
            return float(m.group(1))
    return default


def parse_semantic_constraints(spec_md: str) -> SemanticRuleSet:
    """Parse the ``## Semantic Constraints`` section into a SemanticRuleSet.

    Recognized subsections: ``Domain Coherence``, ``Semantic Coupling Bans``,
    ``Semantic Drift``. Unrecognized lines are silently skipped. ``threshold:``,
    ``max-drift:`` and ``baseline:`` modifiers are optional (defaults apply).
    """
    section = _extract_section(spec_md, "Semantic Constraints")
    if section is None:
        return SemanticRuleSet()

    subs = _split_subsections(section)
    rule_set = SemanticRuleSet()

    coherence_lines = subs.get("domain coherence", [])
    for i, line in enumerate(coherence_lines):
        m = _COHERENCE_RE.search(line.strip())
        if m:
            rule_set.coherence_rules.append(
                DomainCoherenceRule(
                    path_glob=m.group(1).strip(),
                    domain_description=m.group(2).strip(),
                    threshold=_threshold_on_next_lines(coherence_lines, i, default=0.35),
                )
            )

    coupling_lines = subs.get("semantic coupling bans", [])
    for i, line in enumerate(coupling_lines):
        m = _COUPLING_RE.search(line.strip())
        if m:
            rule_set.coupling_rules.append(
                CouplingBanRule(
                    path_glob=m.group(1).strip(),
                    forbidden_description=m.group(2).strip(),
                    threshold=_threshold_on_next_lines(coupling_lines, i, default=0.45),
                )
            )

    for line in subs.get("semantic drift", []):
        m = _DRIFT_RE.search(line.strip())
        if m:
            rule_set.drift_rules.append(
                DriftDetectionRule(
                    path_glob=m.group(1).strip(),
                    baseline_mode=m.group(2).strip().lower(),
                    max_drift=float(m.group(3)) if m.group(3) else 0.25,
                )
            )

    logger.info(
        "Loaded semantic rules: %d coherence, %d coupling, %d drift.",
        len(rule_set.coherence_rules),
        len(rule_set.coupling_rules),
        len(rule_set.drift_rules),
    )
    return rule_set
