# constraint-mcp

> CLAUDE.md rules are wishes. constraint-mcp is the law.

![constraint-mcp demo](demo.gif)

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

## MCP Tools

| Tool | Description |
|------|-------------|
| `check_write(filepath, content)` | Main enforcement gate. Call before every file write. Returns `approved` or a detailed `violation` report. |
| `get_constraints()` | Returns all active rules as structured JSON. Call at session start to load rules into context. |
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
