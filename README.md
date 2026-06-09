# constraint-mcp

[![Listed on ClaudePluginHub](https://www.claudepluginhub.com/badge/christopher-anandaraj-constraint-mcp)](https://www.claudepluginhub.com/plugins/christopher-anandaraj-constraint-mcp?ref=badge)

> CLAUDE.md rules are wishes. constraint-mcp is the law.

![constraint-mcp demo](artifacts/demo.gif)

**Hard enforcement for AI coding agents. SPEC.md rules that actually can't be broken.**

---

## The Problem

CLAUDE.md and system prompts are soft rules. They work by asking the model nicely.

In practice:
- The best frontier models follow [fewer than 30% of prompt-level instructions](https://arxiv.org/abs/2505.16944) in multi-step agent scenarios (AgentIF benchmark, NeurIPS 2025)
- Claude Code had a [documented security bypass](https://adversa.ai/blog/claude-code-security-bypass-deny-rules-disabled/) where deny rules in `.claude.json` were silently skipped when commands exceeded an internal limit (patched in v2.1.90, April 2026)
- Every CLAUDE.md is one context-window flush away from being forgotten

The gap is architectural: rules live in prose and enforcement lives nowhere.

**constraint-mcp closes that gap.** Rules are enforced at the tool level, via AST analysis, *before* writes even happen. The model cannot write a file without calling `check_write()` — and `check_write()` runs the actual code check, not a vibe check.

---

## How It Works

```
Agent wants to write a file
        │
        ▼
  check_write(filepath, content)
        │
        ▼
  AST parse + rule checks
   ┌─────────────────────┐
   │  Banned imports?    │
   │  Protected file?    │
   │  Layer violation?   │
   └─────────────────────┘
        │
   ┌────┴────┐
   │         │
approved   violation
   │         │
   ▼         ▼
file is   violation injected
written   into context window
          (write blocked)
```

The violation message is formatted to be unambiguous in an LLM context: it names the exact rule, the line, and the required fix so that the model knows exactly why the tool was blocked.

---

## Quick Start

```bash
# 1. Install
pip install constraint-mcp

# 2. Create your SPEC.md in the project root (see format below)

# 3. Add to .mcp.json
cat > .mcp.json << 'EOF'
{
  "mcpServers": {
    "constraint-mcp": {
      "command": "constraint-mcp",
      "args": [],
      "env": { "CONSTRAINT_MCP_SPEC": "./SPEC.md" }
    }
  }
}
EOF

# 4. Start Claude Code — constraint-mcp loads automatically
claude
```

---

## Install as a Claude Code plugin

Prefer one command instead of hand-editing `.mcp.json`? Install straight from the marketplace:

```bash
# In any Claude Code session:
/plugin marketplace add Christopher-Anandaraj/ConstraintMCP
/plugin install constraint-mcp@constraint-mcp
```

The plugin ships the MCP server config for you. You still need the `constraint-mcp`
command on your `PATH` (it runs the actual checks), so install the package once:

```bash
pip install constraint-mcp
```

Then drop a `SPEC.md` in your project root and restart Claude Code.

---

## SPEC.md Format

```markdown
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
```

Place `SPEC.md` in your repo root (or set `CONSTRAINT_MCP_SPEC` env var to a custom path). The server hot-reloads whenever SPEC.md changes — no restart needed.

---

## Semantic Constraints (meaning-level enforcement)

AST rules catch *structure* — imports, filepaths, layer boundaries. They can't catch *meaning*: "this file in `src/auth/` is actually doing database work," or "this change quietly turned a utility into something else." Semantic constraints close that gap using embedding similarity (local, CPU-only, no API calls).

![semantic enforcement demo](artifacts/demo_semantic_layer.gif)

```markdown
## Semantic Constraints

### Domain Coherence
- `src/auth/` — must match domain: "authentication, JWT tokens, sessions, login, credentials"
  threshold: 0.45

### Semantic Coupling Bans
- `src/api/` — must not contain: "SQL queries, database connections, ORM, cursor, raw query"
  threshold: 0.58

### Semantic Drift
- `src/core/` — baseline: auto, max-drift: 0.30
- `src/core/auth.py` — baseline: locked, max-drift: 0.15
```

- **Domain Coherence** — code in the path must be *similar enough* to the domain (similarity ≥ threshold).
- **Semantic Coupling Bans** — code in the path must *not resemble* a forbidden concern (similarity ≤ threshold).
- **Semantic Drift** — a file's meaning must not move too far from its baseline. `auto` tracks the file's evolution; `locked` freezes the baseline at the first write.

**Safe by default.** Semantic violations are *warnings* (write approved, `semantic_warnings` attached) until you set `CONSTRAINT_MCP_SEMANTIC_STRICT=true`, which makes them block like AST rules. This lets you observe and tune thresholds before enforcing — embedding similarity is probabilistic, and thresholds are project-specific.

On first use, the embedding model (`BAAI/bge-small-en-v1.5`, ~22MB, Apache 2.0) downloads to `~/.cache/fastembed/`. No GPU, no API key, fully offline after that.

### Semantic env vars

| Variable | Default | Description |
|----------|---------|-------------|
| `CONSTRAINT_MCP_SEMANTIC_STRICT` | `false` | `true` = semantic violations block writes |
| `CONSTRAINT_MCP_SEMANTIC_DISABLED` | `false` | `true` = skip the semantic layer entirely |
| `CONSTRAINT_MCP_SEMANTIC_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model id |
| `CONSTRAINT_MCP_BASELINE_DB` | `.constraint-mcp/baselines.db` | drift baseline store path |

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `check_write(filepath, content)` | Main enforcement gate. Call before every file write. Returns `approved` or a detailed `violation` report (structural or semantic). |
| `get_constraints()` | Returns all active AST rules as structured JSON. Call at session start to load rules into context. |
| `get_semantic_status()` | Returns active semantic rules, files with established drift baselines, and strict-mode state. |
| `report_violation(rule, filepath, line)` | Appends a violation entry to `constraint_violations.log`. |

---

## Comparison

| Feature | CLAUDE.md | aegis-mcp | **constraint-mcp** |
|---------|-----------|-----------|---------------------|
| Enforcement mechanism | Prompt / soft instruction | Tool-level | Tool-level + AST |
| Survives context flush | No | Partial | Yes (tool always runs) |
| Import bans | No | Config-based | AST-verified |
| Protected files | No | Yes | Yes |
| Architecture layer rules | No | No | Yes |
| Semantic / meaning-level rules | No | No | **Yes** |
| Hot-reload on rule change | N/A | No | Yes (watchdog) |
| Violation log | No | No | Yes |
| Setup complexity | Minimal | Low | Low |

---

## Try the Demo

```bash
git clone https://github.com/Christopher-Anandaraj/ConstraintMCP.git
cd ConstraintMCP
pip install -e .
python example/demo.py
```

You'll see all three constraint types fire and be blocked in real time.

---

## License

Apache 2.0
