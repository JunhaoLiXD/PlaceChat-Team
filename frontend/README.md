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

Opening `/rooms/[roomId]` loads that room and rejoins with the persisted session, displaying the nickname returned by the backend. Refreshing, closing/reopening a tab in the same browser profile, disconnecting, and React cleanup never sign out, clear stored authentication, or send Leave. The backend retains a nickname through exactly 60 seconds after the last successful join/heartbeat while `left_at` is null; after that, it assigns a different name. A different browser profile/private session has its own identity.

Each room visit enables Send and starts one 15-second heartbeat only after its own join succeeds, even when a kept-alive Activity preserves an old nickname and draft. Direct submissions are also guarded. A failed join shows its error and keeps sending/heartbeats disabled. Cleanup stops the timer and unsubscribes from Realtime; cancelled joins/history and late channel events are ignored. Count-only updates do not rejoin.

Leave and the All rooms/Back link stop local activity and navigate immediately, even while a join is stalled. Explicit membership cleanup continues with errors handled. Joins and explicit Leaves are ordered per room within the tab, across component/Activity remounts, so an old Leave finishes before a newer join can establish membership. A return to the same room waits for earlier membership requests to settle; Send stays disabled while waiting, and Leave/Back remains usable. Failed cleanup does not block later joins. React cleanup itself never sends Leave, and returning never clears Supabase authentication.

### PBI-34 staging checklist

All live checks below are **pending** until the reviewed change reaches staging; automated tests use mocked Auth/Realtime and do not replace these checks. Use staging's real backend, the same browser profile for returns, and a second independent profile/private session for competing joins. Measure gaps from the last successful heartbeat in Network tools, rather than from tab closure, and keep other tabs for that identity closed so they cannot refresh the hold.

- [ ] **Pending:** Open a room URL, note its nickname, refresh, and confirm the same room/nickname, working messages/history, and continued 15-second heartbeats. No Leave or anonymous sign-in request should occur during refresh.
- [ ] **Pending:** Close the tab and reopen the same URL within 60 seconds of its last successful heartbeat. Confirm the same Supabase identity and backend-returned nickname without a new anonymous sign-in.
- [ ] **Pending:** Close/disconnect the participant beyond 60 seconds since its last heartbeat (for example, 61 seconds); reopen the room URL and confirm a different nickname. Presence may have expired after 30 seconds without ending membership or releasing the nickname early.
- [ ] **Pending:** Click Leave, return to the room immediately, and confirm a different nickname with the same Supabase session. Repeat via All rooms/Back, switch rooms, and revisit a kept-alive room; messages, subscriptions, and heartbeats should work once per active visit.
- [ ] **Pending:** With a preserved draft, return to a kept-alive room after 61 seconds while the rejoin is delayed. Confirm Send and Enter cannot submit until this visit joins; reject the rejoin and confirm its error is visible with sending/heartbeats disabled.
- [ ] **Pending:** Stall the initial join, then click Leave or All rooms/Back. Confirm navigation completes immediately. Return quickly while old requests remain pending: the new join waits for old cleanup, Leave/Back remains usable, and only the new successful visit starts a heartbeat. Check a failed cleanup too.
- [ ] **Pending:** With the first session absent for 59 seconds (also check the inclusive 60-second boundary), join from the second session and confirm it cannot take the held nickname. After expiration or explicit Leave, the released name is available to that other session. Allocation is random, so a browser run alone cannot force reuse; the deterministic backend tests verify eligibility and the exact boundary.

Reconnect catch-up changes (PBI-35) and count-broadcast performance (#91) remain separate work.

## Live messages

`useRoomChannel(roomId, onMessage)` in `src/lib/use-room-channel.ts` joins the room's private Realtime channel and returns its status; `useConnectionBanner(status)` turns that status into the "Connection lost" / "Reconnected" banner. With `NEXT_PUBLIC_USE_MOCKS=true` the chat room uses sample data and does not connect.

## API types

`src/lib/api-types.ts` is generated from the backend's OpenAPI schema, so the frontend uses the exact request and response shapes FastAPI defines ([PlaceChat Technical Design §7.1](../docs/technical-design.md#71-rest-endpoints-prefix-apiv1)). Never edit it by hand. Whoever changes a backend route or Pydantic model regenerates it in the same pull request; otherwise the `api-types` CI check fails:

```bash
cd backend && python scripts/export_openapi.py ../frontend/openapi.json   # backend venv active
cd ../frontend && npm run api-types
```

Commit the updated `src/lib/api-types.ts`. `openapi.json` itself is not committed.

This Next.js version has breaking changes from older releases. Read [AGENTS.md](AGENTS.md) and the docs in `node_modules/next/dist/docs/` before relying on older examples.
