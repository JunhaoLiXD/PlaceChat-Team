import { describe, expect, test } from "vitest";

import { mergeMessages } from "@/lib/messages";
import type { ChatMessage } from "@/lib/placechat-types";

function message(id: string, createdAt: string, body = id): ChatMessage {
  return {
    id,
    room_id: "room-1",
    nickname: "Quiet Otter",
    body,
    created_at: createdAt,
  };
}

describe("mergeMessages", () => {
  test("keeps messages in the order they were sent", () => {
    const merged = mergeMessages(
      [message("b", "2026-10-21T12:00:02Z")],
      [
        message("c", "2026-10-21T12:00:03Z"),
        message("a", "2026-10-21T12:00:01Z"),
      ],
    );

    expect(merged.map((m) => m.id)).toEqual(["a", "b", "c"]);
  });

  test("shows the sender's own message once when the broadcast repeats the POST response", () => {
    const own = { ...message("m1", "2026-10-21T12:00:01Z"), is_mine: true };

    const merged = mergeMessages(
      [own],
      [message("m1", "2026-10-21T12:00:01Z")],
    );

    expect(merged).toEqual([own]);
  });

  test("breaks a timestamp tie by id so the order is stable", () => {
    const same = "2026-10-21T12:00:01Z";

    const merged = mergeMessages([message("y", same)], [message("x", same)]);

    expect(merged.map((m) => m.id)).toEqual(["x", "y"]);
  });

  test("does not change the list it was given", () => {
    const current = [message("a", "2026-10-21T12:00:01Z")];

    mergeMessages(current, [message("b", "2026-10-21T12:00:00Z")]);

    expect(current.map((m) => m.id)).toEqual(["a"]);
  });
});
