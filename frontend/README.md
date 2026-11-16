# PlaceChat frontend

Next.js (App Router) + React + TypeScript + Tailwind CSS. See the root [README](../README.md) for the whole project.

## Run locally

```bash
cp .env.example .env.local   # then fill in the values (ask Junhao)
npm install
npm run dev                  # http://localhost:3000
```

## Checks (the same ones CI runs)

```bash
npm run lint
npm run typecheck
npm test
npm run build
npm run format:check         # npm run format to fix
```

## Browser sessions

Client code can call `ensureSession()` from `src/lib/session.ts` to reuse the stored Supabase session or create an anonymous identity without requesting personal information. Calls in the same tab share in-flight work; browsers supporting Web Locks also serialize first sign-ins across tabs. The shared browser client persists sessions and automatically refreshes tokens.

Call `getAccessToken()` immediately before each authenticated API request rather than keeping an access token in component state; `apiFetch(path, { auth: true })` in `src/lib/placechat-api.ts` does this for you. Public room-list requests do not need a token. These helpers require the frontend Supabase URL and publishable key from `.env.local`; never use a backend secret key.

## Live messages

`useRoomChannel(roomId, onMessage, onMessageRemoved?, onStatus?)` in `src/lib/use-room-channel.ts` joins the room's private Realtime channel and returns its status. Removal remains the third callback from #96; the fourth reports status synchronously so recovery freezes its cursor before batched live arrivals. `useConnectionBanner(status, roomId)` turns that status into the "Connection lost" / "Reconnected" banner. With `NEXT_PUBLIC_USE_MOCKS=true` the chat room uses sample data and does not connect.

### Reconnect recovery (PBI-35)

Supabase owns automatic channel reconnection. After a previously subscribed room loses its connection and resubscribes, the chat fetches `getRoomMessages(roomId, lastId)`. The room visit freezes that cursor synchronously before the gap; live events and delayed send responses cannot move it until history succeeds. With no verified cursor, it requests recent history instead. Initial/duplicate subscription statuses and participant-count updates do not start catch-up or rejoin.

History, live events and send responses use `mergeMessages` for unique IDs, chronological order and preserved ownership. `message.removed` immediately hides a message and records its ID for the visit, preventing delayed history, send responses or live echoes from restoring it. A removed cursor still resolves on the server and does not move the frozen pre-gap cursor. Recovery makes one request plus at most two retries (after 1 and 3 seconds), retains the original cursor after failures or another drop, and offers **Retry messages** if necessary. Requests are serialized within a visit. Each response follows the server's visibility, 7-day retention and newest-20 contract from #96; the frontend does not paginate into older history. Late results from Leave, another room or effect cleanup are ignored.

One 15-second heartbeat per successful join continues with the persisted Supabase session and backend-returned nickname, retrying missed HTTP heartbeats on the next tick. Reconnection does not join again or allocate a name. The 60-second hold remains measured by the server from `last_seen_at`. Explicit Leave/All rooms stops recovery and the heartbeat and navigates immediately. Join/Leave requests are ordered per room across visits/remounts: cleanup follows even a pending Join, later Joins wait until it settles, and failures release the queue. Other rooms remain independent. Refresh, unmount, StrictMode and Activity cleanup only stop local work and unsubscribe, without Leave or sign-out.

Scrolled-up readers retain their position when catch-up inserts earlier messages, including `is_mine` history sent from another tab. Ownership alone never triggers sending-related scrolling. Only submissions acknowledged in the current visit scroll a reader to the bottom, including when the live echo precedes its POST response. Ownership rendering survives Activity returns independently of the current visit's submission IDs.

#### Two-session, 20-second offline check — pending

These live checks have not been run. Use a frontend running this branch and its matching authorized backend/Supabase project:

- [ ] Open the same room in two independent browser profiles, A and B. Record A's backend nickname and a last message ID; confirm A sends one authenticated heartbeat every 15 seconds.
- [ ] Immediately after a successful A heartbeat, put A offline for about 20 seconds. B sends several distinct messages during the interruption. A shows the lost-connection banner.
- [ ] Restore A's connection. Check automatic resubscription, the Reconnected banner, and one history request using the ID from before the gap (recent history if empty). Every missed message in the server's newest-20 window appears once, chronologically, with correct ownership even if a live message arrives first.
- [ ] A retains the same nickname and persisted session, and one heartbeat resumes on the next 15-second tick without another anonymous sign-in or reconnect join. The hold starts at the last successful heartbeat, not at the moment the browser goes offline.
- [ ] Scroll A upward before another short interruption and confirm recovery does not pull it down. Refresh within the hold: history/nickname return, one heartbeat runs, and refresh/cleanup sends no Leave. Explicit Leave/All rooms stops local work and sends Leave.
- [ ] From another tab sharing A's session, send messages while A is offline and scrolled upward. On recovery these historical own messages retain ownership styling, preserve scrolling and show the new-message indicator. A newly submitted message in A still scrolls normally, even if its live echo arrives first.
- [ ] Delay a Leave response, navigate with Leave/Back, and quickly return to that room. Navigation is immediate; the new Join waits for cleanup, then sending and one heartbeat resume. Repeat with a pending initial Join and failed cleanup; another room's Join must stay independent.

#### Parallel PR overlap

This branch merges current `origin/main`, including #96, #97 and #99. PR #95 remains independent. After either feature PR merges, merge the new `main` into the other and reconcile these overlaps:

- PR #95/PBI-34: `src/components/chat-room.tsx`, `src/lib/placechat-api.ts`, `src/lib/use-room-channel.ts`, `__tests__/use-room-channel.test.ts` and this README. Retain one per-room Join/Leave queue and heartbeat, both PRs' cleanup/stale-result guards, #98's recovery/ownership/scrolling and #95's backend nickname-allocation fix. That backend feature is not included here. Keep removal third and status fourth in the hook signature and all call sites.
- Merged PR #96/PBI-27: the component, hook and hook tests conflicted. Both callback/test sets are retained, including visibility/retention and removal during recovery. Merged #97's asynchronous count publisher and #99's reporting/auth/API changes are also retained without feature edits.
- Combined live refresh, Leave/switch and two-session reconnect checks remain pending after integration; all unchecked staging steps above still apply.

## API types

`src/lib/api-types.ts` is generated from the backend's OpenAPI schema, so the frontend uses the exact request and response shapes FastAPI defines ([PlaceChat Technical Design §7.1](../docs/technical-design.md#71-rest-endpoints-prefix-apiv1)). Never edit it by hand. Whoever changes a backend route or Pydantic model regenerates it in the same pull request; otherwise the `api-types` CI check fails:

```bash
cd backend && python scripts/export_openapi.py ../frontend/openapi.json   # backend venv active
cd ../frontend && npm run api-types
```

Commit the updated `src/lib/api-types.ts`. `openapi.json` itself is not committed.

This Next.js version has breaking changes from older releases. Read [AGENTS.md](AGENTS.md) and the docs in `node_modules/next/dist/docs/` before relying on older examples.
