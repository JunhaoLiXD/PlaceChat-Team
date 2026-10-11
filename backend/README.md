# PlaceChat backend

FastAPI on Python 3.13. See the root [README](../README.md) for the whole project.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # then fill in the values (ask Junhao)
uvicorn app.main:app --reload    # http://localhost:8000/health, API docs at /docs
```

## Checks (the same ones CI runs)

```bash
ruff check .
ruff format --check .            # ruff format . to fix
pytest
```

## Layout

| Path | What lives there |
|---|---|
| `app/main.py` | App factory: CORS, error handlers, routers |
| `app/api/` | Routers (HTTP only). Add yours to `api_router` in `app/api/router.py` |
| `app/core/` | Settings, database session, error format, auth, Realtime publisher |
| `app/modules/` | Business rules: `rooms/`, `nicknames/`, `messaging/`, `safety/` |
| `tests/` | pytest tests |

The module contracts from [PlaceChat Technical Design §3.4](../docs/technical-design.md#34-module-contracts) already exist as stubs. Each owner replaces their stub in their own PBI; the docstring of each stub names the owner and the issue. Functions that touch the database take the request's SQLAlchemy session as their first argument, `db`.
