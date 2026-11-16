import { mergeMessages } from "@/lib/messages";
import { getRoomMessages } from "@/lib/placechat-api";
import type { ChatMessage } from "@/lib/placechat-types";
import type { RoomChannelStatus } from "@/lib/use-room-channel";

// One request and two retries per recovery; another real reconnect or Retry
// starts a new bounded attempt using the same, still-unverified gap cursor.
const RETRY_DELAYS_MS = [1_000, 3_000];

/** One room visit, independent of React's batching of status/live events. */
export function createRoomRecovery(
  roomId: string,
  onMessages: (messages: ChatMessage[]) => void,
  onError: (message: string | null) => void,
) {
  let stopped = false;
  let started = false;
  let connected = false;
  let wasConnected = false;
  let initial = true;
  let inFlight = false;
  let revision = 0;
  let attempts = 0;
  let cursor: string | undefined;
  let latest: ChatMessage | undefined;
  let gap: { after: string | undefined } | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;

  function clearRetry() {
    clearTimeout(timer);
    timer = undefined;
  }

  function add(incoming: ChatMessage[]) {
    if (stopped) return;
    const messages = incoming.filter((message) => message.room_id === roomId);
    latest = mergeMessages(latest ? [latest] : [], messages).at(-1);
    if (!initial && !gap) cursor = latest?.id;
    onMessages(messages);
  }

  async function load() {
    if (
      stopped ||
      !started ||
      inFlight ||
      timer !== undefined ||
      (!initial && (!gap || !connected)) ||
      attempts > RETRY_DELAYS_MS.length
    )
      return;
    const requestedRevision = revision;
    const after = initial ? undefined : gap?.after;
    inFlight = true;
    attempts += 1;
    try {
      // The server owns visibility and the newest-20 limit. Do not paginate or
      // use live/send arrivals as a cursor while this gap remains unverified.
      const history = await getRoomMessages(roomId, after);
      if (stopped) return;
      add(history);
      initial = false;
      if (requestedRevision === revision) {
        gap = undefined;
        cursor = latest?.id;
        attempts = 0;
        onError(null);
      }
    } catch {
      if (stopped) return;
      gap ??= { after: cursor };
      onError("Some messages could not be loaded. Please retry.");
      if (
        requestedRevision === revision &&
        attempts <= RETRY_DELAYS_MS.length
      ) {
        timer = setTimeout(
          () => {
            timer = undefined;
            void load();
          },
          RETRY_DELAYS_MS[attempts - 1],
        );
      }
    } finally {
      inFlight = false;
      // An earlier response cannot verify a gap that opened during its fetch.
      if (!stopped && requestedRevision !== revision && connected) {
        attempts = 0;
        void load();
      }
    }
  }

  return {
    add,
    start() {
      started = true;
      void load();
    },
    status(status: RoomChannelStatus) {
      if (stopped) return;
      if (status === "subscribed") {
        if (connected) return; // duplicate SUBSCRIBED
        connected = true;
        if (wasConnected) {
          clearRetry();
          attempts = 0;
          void load();
        }
        wasConnected = true;
      } else if ((status === "error" || status === "closed") && connected) {
        // Freeze before any live messages from a resubscription can arrive.
        gap ??= { after: cursor };
        revision += 1;
        connected = false;
        clearRetry();
      }
    },
    retry() {
      if (inFlight) return;
      clearRetry();
      attempts = 0;
      void load();
    },
    stop() {
      stopped = true;
      clearRetry();
    },
  };
}
