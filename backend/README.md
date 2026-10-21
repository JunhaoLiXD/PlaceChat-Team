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

## Room membership

`POST /api/v1/rooms/{room_id}/join` and `POST /api/v1/rooms/{room_id}/heartbeat` require a Bearer token verified by `get_current_session()`. The caller's session ID comes from that token, never the request body. Join returns `{room: {id, name, description}, nickname}`; heartbeat returns `{status: "ok"}`. Missing or archived rooms return `ROOM_NOT_FOUND` (404). Heartbeat without a joined membership returns `NOT_A_MEMBER` (403).

Join owns one database transaction and first takes a stable, room-specific PostgreSQL transaction advisory lock. Reservations include memberships with `left_at` null and `last_seen_at` at or after the configured 60-second cutoff, including the exact boundary. A held nickname is reused; otherwise the generator receives all reserved names in that room. Each successful join updates `joined_at` and `last_seen_at` and clears `left_at`. Heartbeat updates only `last_seen_at`, with an atomic condition that excludes left memberships.

`ensure_member(db, session_id, room_id)` checks the active room and a joined membership and returns the existing `Membership` contract without committing the caller's transaction. Presence (30 seconds), nickname reservation (60 seconds), and joined membership are separate: a stale heartbeat does not by itself revoke membership. Live participant counts and presence broadcasts remain separate work.

`tests/test_membership.py` uses SQLite for fast HTTP and membership checks. `tests/test_membership_postgres.py` applies the actual room and membership migrations on isolated PostgreSQL and verifies UUID foreign keys, timestamp defaults, the composite primary key, RLS denial for `anon` and `authenticated`, concurrent nickname allocation, transaction lock release, and heartbeat racing a Leave. CI runs both suites with a disposable PostgreSQL 17 service.

To run the PostgreSQL checks locally, use a disposable **local** PostgreSQL server with an admin user allowed to create databases and roles. Create an empty `placechat_pbi07_tests` database there, then set the separate test URL in your shell:

```bash
export PBI07_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/placechat_pbi07_tests
pytest
```

PowerShell: `$env:PBI07_TEST_DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5432/placechat_pbi07_tests'`, then `.venv\Scripts\python.exe -m pytest`. Replace credentials and port with those of your disposable local server. The fixture accepts only loopback URLs naming a `placechat_pbi07_*` database, creates and drops its own UUID-named database, and never reads `DATABASE_URL` or changes the supplied database. Without this test URL, the PostgreSQL checks are reported as skipped. Its minimal `auth.users` table supplies only the UUID foreign key; it does not simulate Supabase Auth.

Before merging, validate on a personal Supabase project if available per [the Supabase README](../supabase/README.md). Remaining live checks are authenticated join/rejoin/heartbeat with real Supabase sessions, RLS through Supabase's browser API, and a staging smoke test after the merged migration deploys automatically. Never push unmerged migrations to shared staging. Leave endpoints, presence counts, and broadcasts belong to their own PBIs.

## Layout

| Path | What lives there |
|---|---|
| `app/main.py` | App factory: CORS, error handlers, routers |
| `app/api/` | Routers (HTTP only). Add yours to `api_router` in `app/api/router.py` |
| `app/core/` | Settings, database session, error format, auth, Realtime publisher |
| `app/modules/` | Business rules: `rooms/`, `nicknames/`, `messaging/`, `safety/` |
| `tests/` | pytest tests |
| `scripts/export_openapi.py` | Exports the OpenAPI schema for the frontend's generated API types. Changed a route or a Pydantic model? See [API types](../frontend/README.md#api-types) |

The module contracts from [PlaceChat Technical Design §3.4](../docs/technical-design.md#34-module-contracts) already exist as stubs. Each owner replaces their stub in their own PBI; the docstring of each stub names the owner and the issue. Functions that touch the database take the request's SQLAlchemy session as their first argument, `db`.
