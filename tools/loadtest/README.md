# Load test

PBI-44 (#79): a Node.js script that connects 50 anonymous clients to one room and checks the targets in Technical Design §9.6.

| Check | Target |
|---|---|
| Delivery time (POST start → received by every other client) | under 1 second at the 95th percentile |
| Every message reaches every other client in the room | no missing deliveries |
| Room isolation | an observer in another room receives nothing; every payload has the right `room_id` and no `session_id` |
| Room list load time, backend awake | under 2 seconds at the 95th percentile |
| Joins and sends | all succeed; nicknames are unique |
| Every simultaneous join (#91) | strictly under 1 second, including the response body |

It also reports join times when all clients join at the same moment.

## How it works

1. Requests `GET /api/v1/rooms` once to wake the backend, then 10 more times to measure the room list.
2. Signs in each client anonymously (its own Supabase user), plus one observer.
3. Subscribes every client to the private `room:{room_id}` channel, and the observer to another room.
4. All clients join at the same moment, then send a heartbeat every 15 seconds.
5. Sends one message every `1/rate` seconds, rotating through the clients, so each client stays far below the rate limit (5 messages in 10 seconds).
6. Waits 5 seconds for late deliveries, then every client leaves.

Results are printed and saved to `results/<run id>.json` (not committed). The exit code is 0 when every check passes and 1 when one fails.

## Run it

Needs Node.js 24. Use an **explicitly authorized test environment whose backend runs the commit under test**. Shared staging runs `main`; before this fix merges, it cannot measure this branch. Match the Supabase Auth/Realtime project to that backend's database and keys. Do not deploy an unmerged branch to shared staging for this check.

```bash
cd tools/loadtest
npm install
PLACECHAT_API_BASE_URL=http://127.0.0.1:8000 npm run loadtest -- --room "Turlington Hall"
```

`npm run loadtest` reads the Supabase URL and publishable key from `frontend/.env.local` (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`). You can set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` instead. Only the public publishable key is used.

| Option | Default | Meaning |
|---|---|---|
| `--room` | (required) | Room name to test |
| `--other-room` | another room | Room for the isolation observer |
| `--clients` | 50 | Number of clients in the room |
| `--duration` | 60 | Seconds of sending |
| `--rate` | 1 | Messages per second, across all clients |
| `--burst-heartbeats` | off | Send every client's heartbeat at the same moment (worst case). By default heartbeats are spread over the 15 seconds, like real users. |

The saved JSON also lists every message's send time and POST time (`perMessage`), every raw join duration (`join.samplesMs`), and when heartbeats were sent (`heartbeatAt`). `config.apiBase` records the measured backend. Optional `PLACECHAT_BACKEND_COMMIT` records the operator-verified checkout SHA; it is a label, not server attestation. Verify the running process/checkout before using it. Thresholds remain strict: every join < 1000 ms, delivery p95 < 1000 ms, room-list p95 < 2000 ms.

## Bug #91 verification (pending)

Normal and burst live runs have **not** been performed against this fix. The controlled-blocking tests do not establish Supabase/network latency. First start the backend from this checkout with an authorized test database/project (backend venv active, environment configured per `backend/README.md`):

```powershell
git rev-parse HEAD
Set-Location backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second shell, from this checkout's `tools/loadtest` directory, verify that the process above runs the printed SHA and use the matching test project's public values:

```powershell
$env:PLACECHAT_API_BASE_URL = 'http://127.0.0.1:8000'
$env:SUPABASE_URL = 'https://<authorized-test-project>.supabase.co'
$env:SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_<authorized-test-key>'
$env:PLACECHAT_BACKEND_COMMIT = (git -C ../.. rev-parse HEAD).Trim()
npm ci
npm run loadtest -- --room "Turlington Hall" --other-room "Norman Hall" --clients 50 --duration 60 --rate 1
npm run loadtest -- --room "Turlington Hall" --other-room "Norman Hall" --clients 50 --duration 60 --rate 1 --burst-heartbeats
```

For a separately authorized hosted environment, replace the API URL with the backend verified to run that same commit. Both runs must pass every check without relaxing thresholds; retain their JSON files as measurements. Until then, the 50-join and burst-delivery performance targets are **pending**, with no claimed measured result.

## Limits to keep in mind

- Supabase limits anonymous sign-ins to 300 per hour per IP address (§6.1). A full run uses 51.
- Supabase's free plan allows about 100 Realtime messages per second. At the default rate, 50 clients receive about 50 per second.
- Test messages (`loadtest <run id> #<n>`) stay in the test room's history.
