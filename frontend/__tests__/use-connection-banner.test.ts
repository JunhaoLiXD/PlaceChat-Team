import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  RESTORED_BANNER_MS,
  useConnectionBanner,
} from "@/lib/use-connection-banner";
import type { RoomChannelStatus } from "@/lib/use-room-channel";

function track(initial: RoomChannelStatus = "connecting") {
  return renderHook(({ status }) => useConnectionBanner(status), {
    initialProps: { status: initial },
  });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useConnectionBanner", () => {
  test("shows nothing while the room first connects", () => {
    const hook = track();
    expect(hook.result.current).toBeNull();

    hook.rerender({ status: "subscribed" });
    expect(hook.result.current).toBeNull();
  });

  test("does not report a loss before the room ever connected", () => {
    const hook = track();

    hook.rerender({ status: "error" });

    expect(hook.result.current).toBeNull();
  });

  test("reports a lost connection, then the reconnect, then hides", () => {
    const hook = track();
    hook.rerender({ status: "subscribed" });

    hook.rerender({ status: "error" });
    expect(hook.result.current).toBe("lost");

    hook.rerender({ status: "connecting" });
    expect(hook.result.current).toBe("lost");

    hook.rerender({ status: "subscribed" });
    expect(hook.result.current).toBe("restored");

    act(() => vi.advanceTimersByTime(RESTORED_BANNER_MS));
    expect(hook.result.current).toBeNull();
  });

  test("treats a closed channel like a lost one", () => {
    const hook = track("subscribed");

    hook.rerender({ status: "closed" });

    expect(hook.result.current).toBe("lost");
  });

  test("goes back to lost if the connection drops again right after", () => {
    const hook = track("subscribed");
    hook.rerender({ status: "error" });
    hook.rerender({ status: "subscribed" });

    hook.rerender({ status: "error" });
    act(() => vi.advanceTimersByTime(RESTORED_BANNER_MS));

    expect(hook.result.current).toBe("lost");
  });
});
