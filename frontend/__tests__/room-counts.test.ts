import { describe, expect, test } from "vitest";

import { applyRoomCount } from "@/components/room-directory";
import { MOCK_ROOMS } from "@/lib/mock-data";

describe("applyRoomCount", () => {
  test("updates only the room named by a count event", () => {
    const updated = applyRoomCount(MOCK_ROOMS, {
      room_id: "library-west",
      count: 3,
    });

    expect(
      updated.find((room) => room.id === "library-west")?.participant_count,
    ).toBe(3);
    expect(
      updated.find((room) => room.id === "reitz-union")?.participant_count,
    ).toBe(42);
    expect(updated).not.toBe(MOCK_ROOMS);
  });

  test("keeps the same state when the event is unchanged or unknown", () => {
    expect(
      applyRoomCount(MOCK_ROOMS, {
        room_id: "library-west",
        count: 24,
      }),
    ).toBe(MOCK_ROOMS);
    expect(
      applyRoomCount(MOCK_ROOMS, { room_id: "missing-room", count: 1 }),
    ).toBe(MOCK_ROOMS);
  });
});
