# Load test

PBI-44 (#79): a Node.js script that connects 50 anonymous clients to one room and checks the targets in Technical Design §9.6.

| Check | Target |
|---|---|
| Delivery time (POST start → received by every other client) | under 1 second at the 95th percentile |
| Every message reaches every other client in the room | no missing deliveries |
| Room isolation | an observer in another room receives nothing; every payload has the right `room_id` and no `session_id` |
| Room list load time, backend awake | under 2 seconds at the 95th percentile |
| Joins and sends | all succeed; nicknames are unique |

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

Needs Node.js 24. Use **staging** only.

```bash
cd tools/loadtest
npm install
PLACECHAT_API_BASE_URL=https://placechat-api-staging.onrender.com npm run loadtest -- --room "Turlington Hall"
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

The saved JSON also lists every message's send time and POST time (`perMessage`) and when heartbeats were sent (`heartbeatAt`), so slow moments can be matched to what the backend was doing.

## Limits to keep in mind

- Supabase limits anonymous sign-ins to 300 per hour per IP address (§6.1). A full run uses 51.
- Supabase's free plan allows about 100 Realtime messages per second. At the default rate, 50 clients receive about 50 per second.
- Test messages (`loadtest <run id> #<n>`) stay in the room's history on staging.
