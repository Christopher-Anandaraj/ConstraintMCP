"""Parse SPEC.md into structured constraint rules."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BannedImport:
    """A single banned import rule."""
    module: str
    reason: str
    scope: str | None = None  # e.g. "src/" restricts rule to that path prefix


@dataclass
class ProtectedFile:
    """A file or directory that must not be written."""
    path: str
    is_directory: bool = False


@dataclass
class ArchitectureRule:
    """A cross-layer import restriction."""
    source_layer: str   # e.g. "src/api/"
    banned_layer: str   # e.g. "src/db/"
    description: str


@dataclass
class ConstraintConfig:
    """All parsed constraints from a SPEC.md file."""
    banned_imports: list[BannedImport] = field(default_factory=list)
    protected_files: list[ProtectedFile] = field(default_factory=list)
    architecture_rules: list[ArchitectureRule] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.banned_imports or self.protected_files or self.architecture_rules)


# Matches:  - No `requests` — use `httpx` only
# Matches:  - No `pickle` anywhere in `src/`
_BANNED_IMPORT_RE = re.compile(
    r"-\s+No\s+`([^`]+)`"           # module name in backticks after "No"
    r"(?:\s+anywhere\s+in\s+`([^`]+)`)?"  # optional "anywhere in `scope`"
    r"(?:\s*[—–-]\s*(.+))?$",       # optional reason after dash
    re.IGNORECASE,
)

# Matches:  - `src/core/auth.py` is read-only
# Matches:  - `config/prod.yaml` must never be modified
# Matches:  - `src/core/` directory is locked
_PROTECTED_FILE_RE = re.compile(
    r"-\s+`([^`]+)`\s+(?:is read-only|must never be modified|is locked|directory is locked)",
    re.IGNORECASE,
)

# Matches:  - Files in `src/api/` must never import from `src/db/` directly
# Matches:  - All database access must go through `src/services/`
_ARCH_RULE_RE = re.compile(
    r"-\s+Files\s+in\s+`([^`]+)`\s+must\s+never\s+import\s+from\s+`([^`]+)`",
    re.IGNORECASE,
)


def _parse_banned_imports(section: str) -> list[BannedImport]:
    results: list[BannedImport] = []
    for line in section.splitlines():
        m = _BANNED_IMPORT_RE.search(line.strip())
        if m:
            module, scope, reason = m.group(1), m.group(2), m.group(3)
            results.append(BannedImport(
                module=module.strip(),
                reason=(reason.strip() if reason else ""),
                scope=(scope.strip() if scope else None),
            ))
    return results


def _parse_protected_files(section: str) -> list[ProtectedFile]:
    results: list[ProtectedFile] = []
    for line in section.splitlines():
        m = _PROTECTED_FILE_RE.search(line.strip())
        if m:
            path = m.group(1).strip()
            results.append(ProtectedFile(path=path, is_directory=path.endswith("/")))
    return results


def _parse_architecture_rules(section: str) -> list[ArchitectureRule]:
    results: list[ArchitectureRule] = []
    for line in section.splitlines():
        m = _ARCH_RULE_RE.search(line.strip())
        if m:
            source, banned = m.group(1).strip(), m.group(2).strip()
            results.append(ArchitectureRule(
                source_layer=source,
                banned_layer=banned,
                description=line.strip().lstrip("- "),
            ))
    return results


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown into H3 section name → content mapping."""
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        h3 = re.match(r"^###\s+(.+)$", line)
        if h3:
            if current_name is not None:
                sections[current_name.lower()] = "\n".join(current_lines)
            current_name = h3.group(1).strip()
            current_lines = []
        elif current_name is not None:
            current_lines.append(line)

    if current_name is not None:
        sections[current_name.lower()] = "\n".join(current_lines)

    return sections


def load_spec(spec_path: str | Path | None = None) -> ConstraintConfig:
    """Load and parse a SPEC.md file into a ConstraintConfig.

    Falls back to CONSTRAINT_MCP_SPEC env var, then ./SPEC.md.
    Returns an empty ConstraintConfig (passthrough mode) if the file is missing.
    """
    if spec_path is None:
        spec_path = os.environ.get("CONSTRAINT_MCP_SPEC", "SPEC.md")

    path = Path(spec_path)
    if not path.exists():
        logger.warning(
            "SPEC.md not found at %s — running in passthrough mode (all writes approved).",
            path.resolve(),
        )
        return ConstraintConfig()

    text = path.read_text(encoding="utf-8")
    sections = _split_sections(text)

    config = ConstraintConfig(
        banned_imports=_parse_banned_imports(sections.get("banned imports", "")),
        protected_files=_parse_protected_files(sections.get("protected files", "")),
        architecture_rules=_parse_architecture_rules(sections.get("architecture rules", "")),
    )

    logger.info(
        "Loaded constraints: %d banned imports, %d protected paths, %d architecture rules.",
        len(config.banned_imports),
        len(config.protected_files),
        len(config.architecture_rules),
    )
    return config
