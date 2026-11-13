// PBI-44 load test (Technical Design §9.6).
//
// Signs in N anonymous clients, joins them all to one room at the same moment,
// subscribes each to the private room channel, and sends messages at a steady
// rate. It reports delivery time (POST start -> receive), room isolation, join
// time, and room-list load time. Exit code 1 when a target is missed.
//
// Usage: npm run loadtest -- --room "The Hub" [--other-room "Norman Hall"]
//        [--clients 50] [--duration 60] [--rate 1]

import { mkdirSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";

import { createClient } from "@supabase/supabase-js";

const TARGETS = { deliveryP95Ms: 1000, roomListP95Ms: 2000, joinMaxMs: 1000 };
const HEARTBEAT_MS = 15_000; // frontend constant, §11
const SUBSCRIBE_TIMEOUT_MS = 20_000;
const GRACE_MS = 5_000; // wait for late deliveries after the last send

const { values: args } = parseArgs({
  options: {
    room: { type: "string" },
    "other-room": { type: "string" },
    clients: { type: "string", default: "50" },
    duration: { type: "string", default: "60" },
    rate: { type: "string", default: "1" },
    // By default heartbeats are spread over the 15 s interval, like real users.
    // With this flag all clients send them at the same moment (worst case).
    "burst-heartbeats": { type: "boolean", default: false },
  },
});

const config = {
  apiBase: (process.env.PLACECHAT_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, ""),
  supabaseUrl: process.env.SUPABASE_URL ?? process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  publishableKey:
    process.env.SUPABASE_PUBLISHABLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "",
  clients: Number(args.clients),
  durationS: Number(args.duration),
  rate: Number(args.rate),
};

function fail(message) {
  console.error(`loadtest: ${message}`);
  process.exit(2);
}

if (!args.room) fail('pass --room "<room name>"');
if (!config.apiBase || !config.supabaseUrl) fail("API base URL and Supabase URL are not set");
// Only the public key is ever used; a secret key would be refused by Supabase anyway.
if (!config.publishableKey.startsWith("sb_publishable_")) fail("publishable key is not set");
if (!(config.clients >= 2 && config.durationS > 0 && config.rate > 0)) fail("bad --clients/--duration/--rate");
// Each sender may send at most 5 messages per 10 s (D1); keep every sender well below that.
if ((config.rate * 10) / config.clients > 2) fail("--rate is too high for the per-session rate limit");

const runId = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
const tag = `loadtest ${runId} #`;

// ---------- helpers ----------

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function percentile(sorted, p) {
  if (sorted.length === 0) return null;
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, index)];
}

function stats(samples) {
  const sorted = [...samples].sort((a, b) => a - b);
  const round = (value) => (value === null ? null : Math.round(value));
  return {
    count: sorted.length,
    p50: round(percentile(sorted, 50)),
    p95: round(percentile(sorted, 95)),
    p99: round(percentile(sorted, 99)),
    max: round(sorted.at(-1) ?? null),
  };
}

async function api(path, { method = "GET", token } = {}) {
  const started = performance.now();
  const response = await fetch(`${config.apiBase}${path}`, {
    method,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const body = response.headers.get("content-type")?.includes("json") ? await response.json() : null;
  const ms = performance.now() - started;
  return { status: response.status, body, ms };
}

async function inBatches(items, size, task) {
  const results = [];
  for (let i = 0; i < items.length; i += size) {
    results.push(...(await Promise.all(items.slice(i, i + size).map(task))));
  }
  return results;
}

/** One simulated browser: its own anonymous user, token, and Realtime socket. */
async function createUser(index) {
  const supabase = createClient(config.supabaseUrl, config.publishableKey, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
  const { data, error } = await supabase.auth.signInAnonymously();
  if (error || !data.session) throw new Error(`sign-in ${index} failed: ${error?.message ?? "no session"}`);
  await supabase.realtime.setAuth(data.session.access_token);
  return { index, supabase, token: data.session.access_token, channel: null, timer: null };
}

function subscribe(user, roomId, onMessage) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(
      () => reject(new Error(`client ${user.index} did not subscribe in time`)),
      SUBSCRIBE_TIMEOUT_MS,
    );
    user.channel = user.supabase
      .channel(`room:${roomId}`, { config: { private: true } })
      .on("broadcast", { event: "message.created" }, ({ payload }) => onMessage(payload, performance.now()))
      .subscribe((state) => {
        // CHANNEL_ERROR (e.g. MissingPartition on the first join of the day) is retried by supabase-js.
        if (state === "SUBSCRIBED") {
          clearTimeout(timeout);
          resolve();
        }
      });
  });
}

// ---------- run ----------

async function main() {
  console.log(`run ${runId}: ${config.clients} clients, ${config.durationS}s at ${config.rate} msg/s`);

  // Room list load time, with the backend awake (the first call wakes it).
  const firstList = await api("/api/v1/rooms");
  if (firstList.status !== 200) fail(`GET /rooms returned ${firstList.status}`);
  const rooms = firstList.body;
  const target = rooms.find((room) => room.name === args.room);
  if (!target) fail(`room "${args.room}" not found`);
  const other = rooms.find((room) => room.name === (args["other-room"] ?? "")) ??
    rooms.find((room) => room.id !== target.id);
  const roomListMs = [];
  for (let i = 0; i < 10; i += 1) roomListMs.push((await api("/api/v1/rooms")).ms);

  console.log(`target "${target.name}", isolation observer in "${other.name}"`);

  const users = await inBatches([...Array(config.clients).keys()], 10, createUser);
  const observer = await createUser("observer");

  const sendStart = new Map(); // seq -> { at, sender }
  const deliveries = []; // ms
  const receivedPairs = new Set(); // `${seq}:${receiver}`
  const problems = { wrongRoom: 0, leakedToOtherRoom: 0, sessionIdInPayload: 0, duplicates: 0 };

  const onTargetMessage = (receiver) => (payload, now) => {
    if (typeof payload?.body !== "string" || !payload.body.startsWith(tag)) return;
    if (payload.room_id !== target.id) problems.wrongRoom += 1;
    if ("session_id" in payload) problems.sessionIdInPayload += 1;
    const seq = Number(payload.body.slice(tag.length));
    const sent = sendStart.get(seq);
    if (!sent || sent.sender === receiver) return;
    const key = `${seq}:${receiver}`;
    if (receivedPairs.has(key)) {
      problems.duplicates += 1;
      return;
    }
    receivedPairs.add(key);
    deliveries.push(now - sent.at);
  };

  await Promise.all(users.map((user) => subscribe(user, target.id, onTargetMessage(user.index))));
  await subscribe(observer, other.id, (payload) => {
    if (typeof payload?.body === "string" && payload.body.startsWith(tag)) problems.leakedToOtherRoom += 1;
  });
  console.log("all channels subscribed");

  // Everyone joins at the same moment (checks the per-room publish queue from PR #85).
  const joins = await Promise.all(users.map((user) => api(`/api/v1/rooms/${target.id}/join`, { method: "POST", token: user.token })));
  const joinErrors = joins.filter((join) => join.status !== 200).map((join) => join.status);
  const observerJoin = await api(`/api/v1/rooms/${other.id}/join`, { method: "POST", token: observer.token });
  if (observerJoin.status !== 200) fail(`observer join returned ${observerJoin.status}`);
  const nicknames = new Set(joins.map((join) => join.body?.nickname).filter(Boolean));
  console.log(`joined: ${joins.length - joinErrors.length}/${joins.length}`);

  const startedAt = performance.now();
  const heartbeatAt = []; // seconds since the send phase started
  users.forEach((user, i) => {
    const offset = args["burst-heartbeats"] ? 0 : (i * HEARTBEAT_MS) / users.length;
    user.startTimer = setTimeout(() => {
      user.timer = setInterval(() => {
        heartbeatAt.push((performance.now() - startedAt) / 1000);
        void api(`/api/v1/rooms/${target.id}/heartbeat`, { method: "POST", token: user.token });
      }, HEARTBEAT_MS);
    }, offset);
  });

  // Send phase: one message every 1/rate seconds, rotating senders.
  const total = Math.round(config.durationS * config.rate);
  const intervalMs = 1000 / config.rate;
  const posts = [];
  const perMessage = []; // { seq, atS, postMs }
  const sendErrors = {};
  const inflight = [];
  for (let seq = 0; seq < total; seq += 1) {
    const due = startedAt + seq * intervalMs;
    const wait = due - performance.now();
    if (wait > 0) await sleep(wait);
    const sender = users[seq % users.length];
    sendStart.set(seq, { at: performance.now(), sender: sender.index });
    inflight.push(
      fetch(`${config.apiBase}/api/v1/rooms/${target.id}/messages`, {
        method: "POST",
        headers: { Authorization: `Bearer ${sender.token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ body: `${tag}${seq}` }),
      }).then((response) => {
        const sent = sendStart.get(seq);
        const postMs = performance.now() - sent.at;
        posts.push(postMs);
        perMessage.push({ seq, atS: Math.round((sent.at - startedAt) / 100) / 10, postMs: Math.round(postMs) });
        if (response.status !== 201) {
          sendErrors[response.status] = (sendErrors[response.status] ?? 0) + 1;
          sendStart.delete(seq);
        }
      }),
    );
  }
  await Promise.all(inflight);
  await sleep(GRACE_MS);

  // Clean up: stop heartbeats, leave, close sockets. Leave frees the nicknames at once.
  for (const user of users) {
    clearTimeout(user.startTimer);
    clearInterval(user.timer);
  }
  await inBatches([...users], 10, (user) => api(`/api/v1/rooms/${target.id}/leave`, { method: "POST", token: user.token }));
  await api(`/api/v1/rooms/${other.id}/leave`, { method: "POST", token: observer.token });
  await Promise.all([...users, observer].map((user) => user.supabase.removeAllChannels()));

  const sentOk = sendStart.size;
  const expected = sentOk * (users.length - 1);
  const result = {
    runId,
    config: {
      apiBase: config.apiBase,
      // Caller-supplied provenance; verify the running backend checkout first.
      backendCommit: process.env.PLACECHAT_BACKEND_COMMIT ?? null,
      clients: config.clients,
      durationS: config.durationS,
      rate: config.rate,
      burstHeartbeats: args["burst-heartbeats"],
      room: target.name,
      otherRoom: other.name,
    },
    join: { ...stats(joins.map((join) => join.ms)), samplesMs: joins.map((join) => join.ms), errors: joinErrors, uniqueNicknames: nicknames.size },
    send: { attempted: total, ok: sentOk, errors: sendErrors, post: stats(posts) },
    delivery: { expected, received: deliveries.length, missing: expected - deliveries.length, ...stats(deliveries) },
    roomList: stats(roomListMs),
    problems,
  };

  const checks = {
    "every join < 1 s": result.join.samplesMs.every((ms) => ms < TARGETS.joinMaxMs),
    "delivery p95 < 1 s": result.delivery.p95 !== null && result.delivery.p95 < TARGETS.deliveryP95Ms,
    "every message delivered": result.delivery.missing === 0,
    "no message in another room": problems.leakedToOtherRoom === 0 && problems.wrongRoom === 0,
    "no session_id in payloads": problems.sessionIdInPayload === 0,
    "room list p95 < 2 s": result.roomList.p95 < TARGETS.roomListP95Ms,
    "all joins and sends succeed": joinErrors.length === 0 && sentOk === total,
    "unique nicknames": nicknames.size === joins.length - joinErrors.length,
  };
  result.checks = checks;

  console.log(JSON.stringify(result, null, 2));
  const slow = perMessage.filter((m) => m.postMs > TARGETS.deliveryP95Ms).sort((a, b) => a.seq - b.seq);
  console.log(`slow sends (> 1 s): ${slow.map((m) => `${m.atS}s=${m.postMs}ms`).join(", ") || "none"}`);
  mkdirSync(new URL("./results/", import.meta.url), { recursive: true });
  const saved = { ...result, perMessage: perMessage.sort((a, b) => a.seq - b.seq), heartbeatAt };
  writeFileSync(new URL(`./results/${runId}.json`, import.meta.url), `${JSON.stringify(saved, null, 2)}\n`);
  for (const [name, ok] of Object.entries(checks)) console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
  process.exit(Object.values(checks).every(Boolean) ? 0 : 1);
}

main().catch((error) => {
  console.error(error);
  process.exit(2);
});
