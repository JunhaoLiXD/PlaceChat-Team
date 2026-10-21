import type { ChatMessage } from "@/lib/placechat-types";

/**
 * Add incoming messages to a room's list, oldest first.
 *
 * The sender sees each of their messages twice (the POST response and the
 * broadcast), and a reconnect refetch can repeat others, so ids are unique.
 * Sorting by `created_at` keeps the order they were sent in (C2).
 */
export function mergeMessages(
  current: ChatMessage[],
  incoming: ChatMessage[],
): ChatMessage[] {
  const byId = new Map(current.map((message) => [message.id, message]));
  for (const message of incoming) {
    byId.set(message.id, { ...byId.get(message.id), ...message });
  }
  return [...byId.values()].sort(
    (a, b) =>
      Date.parse(a.created_at) - Date.parse(b.created_at) ||
      a.id.localeCompare(b.id),
  );
}
