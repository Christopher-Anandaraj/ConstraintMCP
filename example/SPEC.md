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

## Semantic Constraints

### Domain Coherence
- `src/auth/` — must match domain: "authentication, authorization, JWT tokens, sessions, login, credentials, password hashing"
  threshold: 0.45

### Semantic Coupling Bans
- `src/api/` — must not contain: "SQL queries, database connections, ORM models, cursor, raw query, fetchall"
  threshold: 0.58

### Semantic Drift
- `src/core/` — baseline: auto, max-drift: 0.30
