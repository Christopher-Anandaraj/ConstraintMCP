# Changelog

All notable changes to constraint-mcp are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [2.0.0] — 2026-06-09

The semantic enforcement release. constraint-mcp now enforces **meaning**, not
just structure — catching code that is structurally valid but semantically in
the wrong place, or that has drifted from its intended purpose.

### Added

- **Semantic enforcement layer** (`constraint_mcp/semantic/`) running alongside
  the AST checks, using local embedding similarity (`fastembed`,
  `BAAI/bge-small-en-v1.5` — CPU-only, offline, no API keys).
  - **Domain Coherence** — code in a path must be semantically relevant to a
    stated domain (similarity ≥ threshold).
  - **Semantic Coupling Bans** — code in a path must *not* resemble a forbidden
    concern, e.g. no database logic in the API layer (similarity ≤ threshold).
  - **Semantic Drift** — a file's meaning must not stray far from its baseline;
    `auto` tracks evolution, `locked` freezes at the first write.
- New `## Semantic Constraints` section in `SPEC.md` (Domain Coherence,
  Semantic Coupling Bans, Semantic Drift subsections).
- New MCP tool **`get_semantic_status`** — reports active semantic rules, files
  with established drift baselines, and strict-mode state.
- SQLite baseline store for drift detection (`.constraint-mcp/baselines.db`,
  gitignored).
- Environment variables: `CONSTRAINT_MCP_SEMANTIC_STRICT`,
  `CONSTRAINT_MCP_SEMANTIC_DISABLED`, `CONSTRAINT_MCP_SEMANTIC_MODEL`,
  `CONSTRAINT_MCP_BASELINE_DB`.
- New comparison-table row where constraint-mcp is the only tool with
  meaning-level rules.
- Contrast demo (`example/demo_v2.py` + `artifacts/demo_v2.gif`): the same task
  ignored by a CLAUDE.md soft rule vs. blocked at the gate by constraint-mcp.
- 55 new tests (99 total), using real embeddings.

### Changed

- `check_write` now runs structural (AST) checks first, then the semantic layer.
  Violation responses carry a `type` field (`"structural"` or `"semantic"`).
- Demo GIFs and vhs tapes relocated to `artifacts/`.

### Notes

- **Safe by default.** Semantic violations are warnings (write approved, with
  `semantic_warnings` attached) until `CONSTRAINT_MCP_SEMANTIC_STRICT=true`.
- **Fully backward compatible.** A `SPEC.md` with no `## Semantic Constraints`
  section behaves exactly as in 0.1.0; the original 44 tests pass unchanged.
- Embedding thresholds are project-specific and probabilistic — tune them in
  warnings mode before enforcing.
- On first use, the embedding model (~22MB) downloads to `~/.cache/fastembed/`.

## [0.1.0]

Initial release: AST-based structural enforcement — banned imports, protected
files, and cross-layer architecture rules — exposed as the `check_write`,
`get_constraints`, and `report_violation` MCP tools, with SPEC.md hot-reload.
