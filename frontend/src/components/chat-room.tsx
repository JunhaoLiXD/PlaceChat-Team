"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { shouldUseMocks } from "@/lib/config";
import { mergeMessages } from "@/lib/messages";
import {
  heartbeatRoom,
  joinRoom,
  leaveRoom,
  sendRoomMessage,
} from "@/lib/placechat-api";
import type { ChatMessage, RoomSummary } from "@/lib/placechat-types";
import { type RoomChannelStatus, useRoomChannel } from "@/lib/use-room-channel";

const MESSAGE_MAX_LENGTH = 500;
const HEARTBEAT_INTERVAL_MS = 15_000;

const DEMO_MESSAGES: ChatMessage[] = [
  {
    id: "welcome-1",
    room_id: "demo",
    nickname: "Bright Heron",
    body: "Has anyone found a quiet corner nearby?",
    created_at: "2026-10-13T13:42:00-04:00",
  },
  {
    id: "welcome-2",
    room_id: "demo",
    nickname: "Calm Fox",
    body: "The east side has a few open tables right now.",
    created_at: "2026-10-13T13:43:00-04:00",
  },
  {
    id: "welcome-3",
    room_id: "demo",
    nickname: "Bright Heron",
    body: "Perfect, heading over. Thanks! 👋",
    created_at: "2026-10-13T13:44:00-04:00",
  },
];

// The full lost/restored banner and the refetch after reconnecting are PBI-17 (#21).
const CONNECTION_BADGES: Record<
  RoomChannelStatus | "demo",
  { label: string; className: string; dotClassName: string }
> = {
  subscribed: {
    label: "Connected",
    className: "bg-emerald-50 text-emerald-700",
    dotClassName: "bg-emerald-500",
  },
  connecting: {
    label: "Connecting…",
    className: "bg-slate-100 text-slate-600",
    dotClassName: "bg-slate-400",
  },
  error: {
    label: "Reconnecting…",
    className: "bg-amber-50 text-amber-700",
    dotClassName: "bg-amber-500",
  },
  closed: {
    label: "Reconnecting…",
    className: "bg-amber-50 text-amber-700",
    dotClassName: "bg-amber-500",
  },
  demo: {
    label: "Demo data",
    className: "bg-slate-100 text-slate-600",
    dotClassName: "bg-slate-400",
  },
};

function formatMessageTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
  }).format(new Date(value));
}

function MessageBubble({
  message,
  isMine,
}: {
  message: ChatMessage;
  isMine: boolean;
}) {
  return (
    <li className={`flex ${isMine ? "justify-end" : "justify-start"}`}>
      <article
        className={`max-w-[88%] rounded-2xl px-4 py-3 sm:max-w-[72%] ${
          isMine
            ? "rounded-br-md bg-violet-600 text-white shadow-md shadow-violet-200"
            : "rounded-bl-md border border-slate-200 bg-white text-slate-900 shadow-sm"
        }`}
        data-own-message={isMine ? "true" : "false"}
      >
        <div
          className={`flex items-baseline gap-2 text-xs ${
            isMine ? "text-violet-100" : "text-slate-500"
          }`}
        >
          <span className="font-semibold">
            {isMine ? "You" : message.nickname}
          </span>
          <time dateTime={message.created_at}>
            {formatMessageTime(message.created_at)}
          </time>
        </div>
        <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6">
          {message.body}
        </p>
      </article>
    </li>
  );
}

export function MessageFeed({
  messages,
  ownMessageIds,
}: {
  messages: ChatMessage[];
  ownMessageIds: Set<string>;
}) {
  const scrollRegionRef = useRef<HTMLDivElement>(null);
  const previousCountRef = useRef(messages.length);
  const isNearBottomRef = useRef(true);
  const [unreadCount, setUnreadCount] = useState(0);

  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    const region = scrollRegionRef.current;
    if (!region) return;

    if (typeof region.scrollTo === "function") {
      region.scrollTo({ top: region.scrollHeight, behavior });
    } else {
      region.scrollTop = region.scrollHeight;
    }
    isNearBottomRef.current = true;
    setUnreadCount(0);
  };

  useEffect(() => {
    const previousCount = previousCountRef.current;
    if (messages.length <= previousCount) {
      previousCountRef.current = messages.length;
      return;
    }

    const addedMessages = messages.slice(previousCount);
    const onlyOwnMessages = addedMessages.every((message) =>
      ownMessageIds.has(message.id),
    );

    if (isNearBottomRef.current || onlyOwnMessages) {
      requestAnimationFrame(() =>
        scrollToBottom(onlyOwnMessages ? "smooth" : "auto"),
      );
    } else {
      setUnreadCount((count) => count + addedMessages.length);
    }

    previousCountRef.current = messages.length;
  }, [messages, ownMessageIds]);

  const handleScroll = () => {
    const region = scrollRegionRef.current;
    if (!region) return;

    const distanceFromBottom =
      region.scrollHeight - region.scrollTop - region.clientHeight;
    isNearBottomRef.current = distanceFromBottom < 72;
    if (isNearBottomRef.current) {
      setUnreadCount(0);
    }
  };

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scrollRegionRef}
        onScroll={handleScroll}
        data-testid="message-scroll-region"
        className="h-full overflow-y-auto px-4 py-6 sm:px-6"
        aria-label="Messages"
        aria-live="polite"
      >
        <ol className="space-y-4">
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              isMine={ownMessageIds.has(message.id) || message.is_mine === true}
            />
          ))}
        </ol>
      </div>

      {unreadCount > 0 ? (
        <button
          type="button"
          onClick={() => scrollToBottom()}
          className="absolute bottom-4 left-1/2 min-h-10 -translate-x-1/2 rounded-full bg-slate-950 px-4 text-xs font-semibold text-white shadow-lg transition hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-950"
        >
          {unreadCount} new {unreadCount === 1 ? "message" : "messages"} ↓
        </button>
      ) : null}
    </div>
  );
}

export function ChatRoom({ room }: { room: RoomSummary }) {
  const mockMode = shouldUseMocks();
  const [nickname, setNickname] = useState<string | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);
  // Real rooms start empty until the history endpoint (C3, Sprint 2) exists.
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    mockMode
      ? DEMO_MESSAGES.map((message) => ({ ...message, room_id: room.id }))
      : [],
  );
  const [ownMessageIds, setOwnMessageIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isLeaving, setIsLeaving] = useState(false);
  const router = useRouter();

  const trimmedDraft = draft.trim();
  const messageLength = Array.from(trimmedDraft).length;
  const isTooLong = messageLength > MESSAGE_MAX_LENGTH;
  const canSend =
    nickname !== null && messageLength > 0 && !isTooLong && !isSending;

  const participantLabel = useMemo(
    () =>
      `${room.participant_count} ${room.participant_count === 1 ? "person" : "people"} here`,
    [room.participant_count],
  );

  const channelStatus = useRoomChannel(mockMode ? null : room.id, (message) =>
    setMessages((current) => mergeMessages(current, [message])),
  );
  const badge = CONNECTION_BADGES[mockMode ? "demo" : channelStatus];

  useEffect(() => {
    let cancelled = false;

    async function join() {
      try {
        const result = await joinRoom(room.id);
        if (!cancelled) {
          setNickname(result.nickname);
        }
      } catch (caught) {
        if (!cancelled) {
          setJoinError(
            caught instanceof Error
              ? caught.message
              : "We couldn’t join this room.",
          );
        }
      }
    }

    void join();

    return () => {
      cancelled = true;
    };
  }, [room]);

  useEffect(() => {
    if (!nickname) return;

    const interval = window.setInterval(() => {
      void heartbeatRoom(room.id).catch(() => {
        // PBI-17 owns the full reconnect flow. The reserved status area remains visible.
      });
    }, HEARTBEAT_INTERVAL_MS);

    return () => window.clearInterval(interval);
  }, [nickname, room.id]);

  const handleSubmit = async (event?: FormEvent) => {
    event?.preventDefault();
    setSendError(null);

    if (messageLength === 0) return;

    if (isTooLong) {
      setSendError(`Messages can be up to ${MESSAGE_MAX_LENGTH} characters.`);
      return;
    }

    if (!nickname) {
      setSendError("Wait a moment while we finish joining the room.");
      return;
    }

    setIsSending(true);

    try {
      const sentMessage = await sendRoomMessage(
        room.id,
        trimmedDraft,
        nickname,
      );
      setOwnMessageIds((ids) => new Set(ids).add(sentMessage.id));
      // The broadcast of this message may arrive first; merging keeps one copy.
      setMessages((current) => mergeMessages(current, [sentMessage]));
      setDraft("");
    } catch (caught) {
      setSendError(
        caught instanceof Error
          ? caught.message
          : "Your message couldn’t be sent.",
      );
    } finally {
      setIsSending(false);
    }
  };

  // Leave frees the nickname right away (§5.2). Unmounting the page then closes the
  // channel and stops the heartbeat, so no more messages arrive from this room.
  const handleLeave = async (event?: MouseEvent) => {
    event?.preventDefault();
    if (isLeaving) return;
    setIsLeaving(true);

    if (nickname) {
      try {
        await leaveRoom(room.id);
      } catch {
        // Still go back: presence times out after 30 seconds without heartbeats.
      }
    }
    router.push("/");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
  };

  return (
    <main className="flex min-h-screen flex-col bg-slate-100/80">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link
            href="/"
            onClick={(event) => void handleLeave(event)}
            className="inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="h-4 w-4"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="m15 18-6-6 6-6"
              />
            </svg>
            <span className="hidden sm:inline">All rooms</span>
            <span className="sm:hidden">Back</span>
          </Link>

          <div className="min-w-0 text-center">
            <h1 className="truncate text-sm font-bold text-slate-950 sm:text-base">
              {room.name}
            </h1>
            <p className="text-xs text-slate-500">{participantLabel}</p>
          </div>

          <button
            type="button"
            onClick={() => void handleLeave()}
            disabled={isLeaving}
            className="min-h-10 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 disabled:cursor-not-allowed disabled:text-slate-400"
          >
            {isLeaving ? "Leaving…" : "Leave"}
          </button>
        </div>
      </header>

      <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col p-3 sm:p-6">
        <section className="flex min-h-[calc(100vh-5.5rem)] flex-1 flex-col overflow-hidden rounded-3xl border border-slate-200 bg-slate-50 shadow-xl shadow-slate-200/70 sm:min-h-[calc(100vh-7rem)]">
          <div className="flex min-h-14 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 sm:px-6">
            <div className="min-w-0">
              {nickname ? (
                <p className="truncate text-sm text-slate-600">
                  You are{" "}
                  <span className="font-bold text-slate-950">{nickname}</span>
                </p>
              ) : (
                <p className="text-sm text-slate-500">
                  {joinError ?? "Finding your nickname…"}
                </p>
              )}
            </div>
            <div
              role="status"
              className={`inline-flex shrink-0 items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${badge.className}`}
            >
              <span
                className={`h-2 w-2 rounded-full ${badge.dotClassName}`}
                aria-hidden="true"
              />
              {badge.label}
            </div>
          </div>

          <MessageFeed messages={messages} ownMessageIds={ownMessageIds} />

          <div className="border-t border-slate-200 bg-white p-3 sm:p-4">
            <p className="mb-2 px-1 text-xs text-slate-500">
              Keep it kind. Don’t share personal information, and report
              anything unsafe.
            </p>

            <form
              onSubmit={handleSubmit}
              className="rounded-2xl border border-slate-200 bg-slate-50 p-2 focus-within:border-violet-400 focus-within:ring-4 focus-within:ring-violet-100"
            >
              <label htmlFor="message" className="sr-only">
                Message {room.name}
              </label>
              <textarea
                id="message"
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setSendError(null);
                }}
                onKeyDown={handleKeyDown}
                rows={2}
                placeholder={`Message ${room.name}`}
                className="max-h-36 min-h-16 w-full resize-none bg-transparent px-2 py-1.5 text-sm leading-6 text-slate-950 outline-none placeholder:text-slate-400"
                aria-describedby="message-help message-error"
              />

              <div className="flex items-center justify-between gap-3 px-1 pb-1">
                <p
                  id="message-help"
                  className={`text-xs font-medium ${isTooLong ? "text-rose-600" : "text-slate-400"}`}
                >
                  {messageLength} / {MESSAGE_MAX_LENGTH}
                </p>
                <button
                  type="submit"
                  disabled={!canSend}
                  className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-violet-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-600 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none"
                >
                  {isSending ? "Sending…" : "Send"}
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className="h-4 w-4"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="m5 12 14-7-4 14-3-5-7-2Zm7 2 7-9"
                    />
                  </svg>
                </button>
              </div>
            </form>

            <div id="message-error" className="min-h-5 px-1 pt-1.5">
              {isTooLong ? (
                <p role="alert" className="text-xs font-medium text-rose-600">
                  Messages can be up to {MESSAGE_MAX_LENGTH} characters after
                  trimming.
                </p>
              ) : sendError ? (
                <p role="alert" className="text-xs font-medium text-rose-600">
                  {sendError}
                </p>
              ) : (
                <p className="text-xs text-slate-400">
                  Press Enter to send · Shift+Enter for a new line
                </p>
              )}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
