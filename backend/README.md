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

Every existing `/api/v1/admin/rooms` operation uses `require_admin()` on its router. The dependency verifies the Bearer token through `get_current_session()` (ES256 signature, expiry, audience, and issuer), then uses the request's `get_db` session to check `admin_users`. Missing, invalid, or expired tokens return `UNAUTHENTICATED` (401). Anonymous sessions, including any accidentally added to the allow-list, and unlisted users return `FORBIDDEN` (403). A listed non-anonymous session receives the existing `Admin(user_id)` contract. Each request checks the allow-list again, so removing an entry revokes access without waiting for its token to expire.

Junhao provisions Supabase email/password users and their `admin_users` entries. The migration creates an empty allow-list with RLS enabled and no policies; browsers cannot read it or grant privileges. There is no public sign-up or automatic admin creation. The login page belongs to PBI-23. Deleting a provisioned Auth user removes that user's allow-list entry through its foreign key.

`tests/test_auth.py` exercises real authorization on every existing admin operation using locally signed ES256 tokens and an isolated SQLite database, with only the JWKS and broadcast transports replaced. `tests/test_admin_auth_postgres.py` validates the actual migration, allow-list lookup, and RLS denial for `anon` and `authenticated` on disposable PostgreSQL. Full Supabase email/password sign-in and staging admin-operation smoke tests remain live checks after Junhao provisions an account and the merged migration deploys.

The admin migration is newer than `20261021031518_create_messages.sql` from PR #44. Coordinate merge/deployment ordering with Junhao so any older pending migrations are applied first. Do not edit merged migrations or push migrations to staging from a development machine.

## Room membership

`POST /api/v1/rooms/{room_id}/join`, `POST /api/v1/rooms/{room_id}/heartbeat`, and `POST /api/v1/rooms/{room_id}/leave` require a Bearer token verified by `get_current_session()`. The caller's session ID comes from that token, never the request body. Join returns `{room: {id, name, description}, nickname}`; heartbeat and leave return `{status: "ok"}`. Missing or archived rooms return `ROOM_NOT_FOUND` (404). Heartbeat or leave without a joined membership (including an already-left membership) returns `NOT_A_MEMBER` (403).

Join owns one database transaction and first takes a stable, room-specific PostgreSQL transaction advisory lock. Reservations include memberships with `left_at` null and `last_seen_at` at or after the configured 60-second cutoff, including the exact boundary. A held nickname is reused; otherwise the generator receives all reserved names in that room. Each successful join updates `joined_at` and `last_seen_at` and clears `left_at`. Heartbeat updates only `last_seen_at`, with an atomic condition that excludes left memberships.

Leave takes the same room lock in one transaction and sets only the caller's `left_at` in that room. It releases the nickname immediately, including when the caller has already timed out of presence. The caller's next join allocates a different nickname; the old name remains available to other sessions. A concurrent heartbeat cannot clear `left_at`. Join, leave, heartbeat, and the presence sweeper follow the same room-lock order and hold a shared row lock on the active room so an archive cannot race their changes. Each operation samples time after acquiring the room lock.

`ensure_member(db, session_id, room_id)` checks the active room and a joined membership and returns the existing `Membership` contract without committing the caller's transaction. Presence (30 seconds), nickname reservation (60 seconds), and joined membership are separate: a stale heartbeat does not by itself revoke membership. Public `GET /api/v1/rooms` counts only memberships with `left_at` null and `last_seen_at >= now - PRESENCE_TIMEOUT_SECONDS` (30 by default). The exact boundary is included, empty rooms return count 0, and archived rooms remain excluded. Counts are fetched in one query with one cutoff for the whole response.

### Live participant counts (PBI-29)

After a changed count commits, the backend notifies its background count publisher for both private channels:

| Channel | Event | Exact payload |
|---|---|---|
| `room:{room_id}` | `presence.updated` | `{"count": 2}` |
| `rooms` | `room.count` | `{"room_id": "<uuid>", "count": 2}` |

These are absolute integer counts, including zero, and never contain session IDs. The REST presence predicate above remains the source of truth. `room_presence_counts` stores the last observed count to suppress unchanged updates, including after restart. The snapshot is reconciled in the membership transaction under the room lock. A revision is reserved there, but no work is queued until commit succeeds. Join, leave, heartbeat, and sweeps then return after a short notification: no request waits for network I/O or an earlier publisher.

FastAPI's lifespan owns one async publisher task and its own pooled HTTP client, separate from message requests and FastAPI's shared thread pool. There is at most one pending value per room, one in-flight delivery, and one scheduled wakeup. State is O(number of rooms), never O(number of requests): one committed revision and two last-delivered channel counts per room, plus the coalesced pending value. Newer committed revisions replace pending values; older notifications are rejected even after delivery, so delayed post-commit work cannot overwrite a newer count. Rollbacks never notify. Intermediate counts may be coalesced; the final successful delivery converges to the latest committed count, including zero. Each channel is attempted independently, successful channel counts are deduplicated, and failures are logged without failing membership requests. Unexpected delivery failures do not kill the worker. Shutdown first stops the sweeper, then drains publication for up to five seconds; at the deadline async HTTP work is cancelled and its client is closed. No blocked publisher threads are left behind. This remains a single-backend-process design.

Pending timeouts can be included in the same observation as a join or leave. If their combined effect leaves the count unchanged, no notification is sent. Publication remains best effort, not a durable outbox: clients initialize counts with `GET /api/v1/rooms` and refetch after reconnecting to recover missed events. Chuks owns that display in PBI-28.

FastAPI's lifespan starts one sweeper for the single backend instance. It sweeps on startup, then waits `SWEEPER_INTERVAL_SECONDS` (10 by default) between iterations. Discovery and each room use separate, short-lived sessions. Only synchronous database work runs in the thread pool; count HTTP publication runs in the owned async task. One room's failure does not prevent the remaining rooms from being processed, and a failed iteration is logged and retried on the next interval. Shutdown wakes an idle sweeper and waits for an in-flight database iteration to finish and close its session.

A participant is present at exactly 30 seconds and expires only after that boundary. A timeout is observed on the next sweep, up to one configured interval later under normal operation. Sweeps update only the count snapshot: they never set `left_at`, delete membership, change `last_seen_at`, or release a 60-second nickname hold. A rejoin or resumed heartbeat restores presence, and unchanged later sweeps do not repeat the timeout event.

`tests/test_membership.py` controls the clock and mocks broadcasts to verify event payloads, boundaries, deduplication, returning participants, nickname reservations, rollback, and publication failures. `tests/test_presence_sweeper.py` checks lifespan ownership, shutdown, thread-pool execution, error recovery, and session cleanup. Ordinary request tests disable background sweeps so they cannot read a developer's configured application database. Real broadcast transport is blocked throughout the suite. The PostgreSQL membership suite also verifies snapshot RLS and constraints, released advisory locks during publication, and concurrent sweeper/join/leave/heartbeat activity in both transaction orders.

Count assertions wait at explicit delivery checkpoints; concurrent tests allow only valid coalesced sequences and still assert the final count and exact payloads on both channels. `tests/test_presence_publisher.py` controls stalled I/O to verify the per-room bound, final zero, late notifications, independent channel failures, worker recovery, exclusive ownership, and bounded shutdown. HTTP tests prove membership requests and sweeps finish while publication is stalled. Isolated PostgreSQL tests also delay real post-commit notifications and complete 50 joins before releasing the publisher. These are correctness checks, not live latency measurements. Normal and burst load checks for #91 remain **pending** against an authorized backend actually running this branch; see the [exact load commands](../tools/loadtest/README.md#bug-91-verification-pending).

`tests/test_membership.py` and `tests/test_rooms.py` use SQLite for fast HTTP, membership, and presence checks. `tests/test_auth.py` verifies signed-token authorization for Leave. `tests/test_membership_postgres.py` applies the actual room and membership migrations on isolated PostgreSQL and verifies UUID foreign keys, timestamp defaults, the composite primary key, RLS denial for `anon` and `authenticated`, concurrent nickname allocation, transaction lock release, presence boundaries, and leave isolation between rooms and users. Heartbeat/leave and join/leave races run in both commit orders, including joins by the same session and other sessions. Deleting an Auth user cascades to that user's memberships, including historical memberships; a PostgreSQL regression test verifies that other memberships, users, and rooms stay intact. CI runs both suites with a disposable PostgreSQL 17 service.

To run the PostgreSQL checks locally, use a disposable **local** PostgreSQL server with an admin user allowed to create databases and roles. Create an empty `placechat_pbi07_tests` database there, then set the separate test URL in your shell:

```bash
export TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/placechat_pbi07_tests
pytest
```

PowerShell: `$env:TEST_DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5432/placechat_pbi07_tests'`, then `.venv\Scripts\python.exe -m pytest`. Replace credentials and port with those of your disposable local server. The shared fixture in `tests/conftest.py` applies the room, membership, administrator, and presence-count snapshot migrations for each PostgreSQL test module. It accepts only loopback URLs naming a `placechat_pbi07_*` database and rejects URL query parameters. It creates and drops its own UUID-named database, and never reads or falls back to `DATABASE_URL` or changes the supplied database. Without this test URL, the PostgreSQL checks are reported as skipped. Its minimal `auth.users` table supplies only the UUID foreign key; it does not simulate Supabase Auth.

Before merging, validate on a personal Supabase project if available per [the Supabase README](../supabase/README.md). Remaining live checks are authenticated join/leave/rejoin/heartbeat and public count changes with real Supabase sessions, RLS through Supabase's browser API, and a staging smoke test after deployment. Never push unmerged migrations to shared staging. PBI-29 adds `20261109120000_create_room_presence_counts.sql`; it must land through the normal reviewed migration workflow before running the new backend on staging.

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
