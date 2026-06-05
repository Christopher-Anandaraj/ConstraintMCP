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
