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

## Administrator console

Provisioned administrators sign in with email and password at `/admin/login`. The login form uses Supabase Auth, then verifies administrator access through the protected API before opening `/admin/rooms`. The room page lists active and archived rooms and supports creating, editing, and archiving active rooms. Browser-side checks are only user guidance; every admin API operation independently verifies the Bearer token and the database allow-list.

On `/admin/reports`, **Block sender** opens a duration selector with **15 minutes**,
**1 hour**, and **24 hours**. Confirming uses the protected API and displays the
effective expiration in Eastern Time. Blocking applies across all rooms and leaves
the report available for separate removal or dismissal. Controls stay disabled while
the request is pending; failures are shown with retry available. The chat composer's
expiry display and automatic re-enable behavior remain in PBI-43 (#78).

**Pending live check after deployment:** In two independent browser profiles, have a
sender join two rooms and post in one. Report that message from the other profile.
As an administrator, block its sender from Reports with a chosen duration and check
the confirmation. In the sender's profile, posting in either joined room must return
403 `BLOCKED` with `error.until`; the reporter must still be able to send. Confirm
the sender's API request succeeds after expiration. Automated tests control the
clock to cover the exact boundary without waiting 15 minutes.

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

#### Combined PBI-34 and PBI-35 behavior

This branch merges current `origin/main`, including #95's persisted-session nickname rules, #96's visible history/7-day retention and removals, #97's asynchronous count publisher, #99's reporting/auth/API changes, #100's report moderation and #101's word filter. The component shares one visit guard for sending readiness, heartbeat and recovery; `placechat-api.ts` provides the canonical per-room Join/Leave queue. The recovery controller owns removed IDs for history, send responses and live echoes. In `useRoomChannel` and its callers, `onMessageRemoved` is third and synchronous `onStatus` is fourth. History failures leave the joined nickname and sending controls available while offering bounded retries.

Combined live refresh, expiration, Leave/switch and two-session reconnect checks remain pending; all unchecked staging steps above still apply. PR #102's dependency upgrade is separate until it merges into `main`; a security-blocked build must be reported without disabling the check.

## API types

`src/lib/api-types.ts` is generated from the backend's OpenAPI schema, so the frontend uses the exact request and response shapes FastAPI defines ([PlaceChat Technical Design §7.1](../docs/technical-design.md#71-rest-endpoints-prefix-apiv1)). Never edit it by hand. Whoever changes a backend route or Pydantic model regenerates it in the same pull request; otherwise the `api-types` CI check fails:

```bash
cd backend && python scripts/export_openapi.py ../frontend/openapi.json   # backend venv active
cd ../frontend && npm run api-types
```

Commit the updated `src/lib/api-types.ts`. `openapi.json` itself is not committed.

This Next.js version has breaking changes from older releases. Read [AGENTS.md](AGENTS.md) and the docs in `node_modules/next/dist/docs/` before relying on older examples.
