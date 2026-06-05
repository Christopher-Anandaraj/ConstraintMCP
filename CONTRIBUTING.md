# Contributing to constraint-mcp

Thanks for wanting to make AI coding agents less chaotic.

## Getting started

```bash
git clone https://github.com/Christopher-Anandaraj/ConstraintMCP.git
cd ConstraintMCP
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pip install pytest
pytest tests/ -v
```

All 44 tests should pass before you open a PR.

## What's in scope

- New constraint types in `enforcer.py` (e.g. regex-based content checks, file size limits)
- Support for additional languages in the AST layer (currently Python only)
- Better SPEC.md parsing for edge cases
- Performance improvements to `check_write` (it runs on every write, keep it fast)
- Bug fixes and test coverage gaps

## What's out of scope (for now)

- GUI or web dashboard
- Cloud/SaaS features
- Integrations with specific IDEs beyond MCP

## Making a change

1. Open an issue first for anything non-trivial so we can align before you write code
2. Fork → branch → PR against `main`
3. Add tests for whatever you change — the enforcer and parser both have good coverage to model after
4. Keep PRs focused; one thing per PR

## Reporting a bug

Open an issue with:
- Your `SPEC.md` (or the relevant rules)
- The file content that triggered the wrong result
- What `check_write()` returned vs. what you expected

## Questions

Open a GitHub Discussion. Issues are for bugs and tracked work only.
