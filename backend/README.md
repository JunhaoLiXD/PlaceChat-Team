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

## Administrator authentication

Every `/api/v1/admin/rooms` operation uses `require_admin()` on its router. The authenticated `GET` lists active and archived rooms for the admin console; `POST`, `PATCH`, and the archive operation mutate them. The dependency verifies the Bearer token through `get_current_session()` (ES256 signature, expiry, audience, and issuer), then uses the request's `get_db` session to check `admin_users`. Missing, invalid, or expired tokens return `UNAUTHENTICATED` (401). Anonymous sessions, including any accidentally added to the allow-list, and unlisted users return `FORBIDDEN` (403). A listed non-anonymous session receives the existing `Admin(user_id)` contract. Each request checks the allow-list again, so removing an entry revokes access without waiting for its token to expire.

Junhao provisions Supabase email/password users and their `admin_users` entries. The migration creates an empty allow-list with RLS enabled and no policies; browsers cannot read it or grant privileges. There is no public sign-up or automatic admin creation. The login and room-management pages are implemented by PBI-23. Deleting a provisioned Auth user removes that user's allow-list entry through its foreign key.

`tests/test_auth.py` exercises real authorization on every existing admin operation using locally signed ES256 tokens and an isolated SQLite database, with only the JWKS and broadcast transports replaced. `tests/test_admin_auth_postgres.py` validates the actual migration, allow-list lookup, and RLS denial for `anon` and `authenticated` on disposable PostgreSQL. Full Supabase email/password sign-in and staging admin-operation smoke tests remain live checks after Junhao provisions an account and the merged migration deploys.

The admin migration is newer than `20261021031518_create_messages.sql` from PR #44. Coordinate merge/deployment ordering with Junhao so any older pending migrations are applied first. Do not edit merged migrations or push migrations to staging from a development machine.

## Room membership

`POST /api/v1/rooms/{room_id}/join`, `POST /api/v1/rooms/{room_id}/heartbeat`, and `POST /api/v1/rooms/{room_id}/leave` require a Bearer token verified by `get_current_session()`. The caller's session ID comes from that token, never the request body. Join returns `{room: {id, name, description}, nickname}`; heartbeat and leave return `{status: "ok"}`. Missing or archived rooms return `ROOM_NOT_FOUND` (404). Heartbeat or leave without a joined membership (including an already-left membership) returns `NOT_A_MEMBER` (403).

Join owns one database transaction and first takes a stable, room-specific PostgreSQL transaction advisory lock. Reservations include memberships with `left_at` null and `last_seen_at` at or after the configured 60-second cutoff, including the exact boundary. A held nickname is reused; otherwise the generator receives all reserved names in that room. Each successful join updates `joined_at` and `last_seen_at` and clears `left_at`. Heartbeat updates only `last_seen_at`, with an atomic condition that excludes left memberships.

Leave takes the same room lock in one transaction and sets only the caller's `left_at` in that room. It releases the nickname immediately, including when the caller has already timed out of presence. The caller's next join allocates a different nickname; the old name remains available to other sessions. A concurrent heartbeat cannot clear `left_at`, and concurrent join/leave operations follow their room-lock order. Both join and leave hold a shared row lock on the active room so an archive cannot race the membership change.

`ensure_member(db, session_id, room_id)` checks the active room and a joined membership and returns the existing `Membership` contract without committing the caller's transaction. Presence (30 seconds), nickname reservation (60 seconds), and joined membership are separate: a stale heartbeat does not by itself revoke membership. Public `GET /api/v1/rooms` counts only memberships with `left_at` null and `last_seen_at >= now - PRESENCE_TIMEOUT_SECONDS` (30 by default). The exact boundary is included, empty rooms return count 0, and archived rooms remain excluded. Counts are fetched in one query with one cutoff for the whole response. Live count broadcasts and the sweeper belong to PBI-29; frontend Leave controls belong to PBI-24.

`tests/test_membership.py` and `tests/test_rooms.py` use SQLite for fast HTTP, membership, and presence checks. `tests/test_auth.py` verifies signed-token authorization for Leave. `tests/test_membership_postgres.py` applies the actual room and membership migrations on isolated PostgreSQL and verifies UUID foreign keys, timestamp defaults, the composite primary key, RLS denial for `anon` and `authenticated`, concurrent nickname allocation, transaction lock release, presence boundaries, and leave isolation between rooms and users. Heartbeat/leave and join/leave races run in both commit orders, including joins by the same session and other sessions. Deleting an Auth user cascades to that user's memberships, including historical memberships; a PostgreSQL regression test verifies that other memberships, users, and rooms stay intact. CI runs both suites with a disposable PostgreSQL 17 service.

To run the PostgreSQL checks locally, use a disposable **local** PostgreSQL server with an admin user allowed to create databases and roles. Create an empty `placechat_pbi07_tests` database there, then set the separate test URL in your shell:

```bash
export TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/placechat_pbi07_tests
pytest
```

PowerShell: `$env:TEST_DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5432/placechat_pbi07_tests'`, then `.venv\Scripts\python.exe -m pytest`. Replace credentials and port with those of your disposable local server. The shared fixture in `tests/conftest.py` applies the room, membership, and administrator migrations for each PostgreSQL test module. It accepts only loopback URLs naming a `placechat_pbi07_*` database and rejects URL query parameters. It creates and drops its own UUID-named database, and never reads or falls back to `DATABASE_URL` or changes the supplied database. Without this test URL, the PostgreSQL checks are reported as skipped. Its minimal `auth.users` table supplies only the UUID foreign key; it does not simulate Supabase Auth.

Before merging, validate on a personal Supabase project if available per [the Supabase README](../supabase/README.md). Remaining live checks are authenticated join/leave/rejoin/heartbeat and public count changes with real Supabase sessions, RLS through Supabase's browser API, and a staging smoke test after deployment. Never push unmerged migrations to shared staging. PBI-25 adds no migrations.

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
