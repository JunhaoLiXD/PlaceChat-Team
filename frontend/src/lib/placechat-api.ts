import { MOCK_ROOMS } from "@/lib/mock-data";
import { publicConfig, shouldUseMocks } from "@/lib/config";
import type {
  ApiErrorBody,
  ChatMessage,
  JoinRoomResult,
  RoomSummary,
} from "@/lib/placechat-types";
import { getAccessToken } from "@/lib/session";

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

interface ApiRequest extends RequestInit {
  /** Send the current Supabase access token (Technical Design §6.3). */
  auth?: boolean;
}

async function apiFetch<T>(
  path: string,
  { auth = false, ...init }: ApiRequest = {},
): Promise<T> {
  // Read the session before every call; supabase-js refreshes the token, so never cache it.
  const authorization: Record<string, string> = auth
    ? { Authorization: `Bearer ${await getAccessToken()}` }
    : {};
  let response: Response;

  try {
    response = await fetch(`${publicConfig.apiBaseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...authorization,
        ...init.headers,
      },
    });
  } catch {
    throw new ApiRequestError(
      "The server is unavailable. Please try again.",
      0,
    );
  }

  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // A proxy or platform error may not use the API's JSON error shape.
    }

    throw new ApiRequestError(
      body?.error?.message ?? "Something went wrong. Please try again.",
      response.status,
      body?.error?.code,
    );
  }

  return (await response.json()) as T;
}

export async function listRooms(): Promise<RoomSummary[]> {
  // Local development can opt into deterministic rooms, but configured
  // deployments must surface real API failures.
  if (shouldUseMocks()) {
    return MOCK_ROOMS;
  }

  return apiFetch<RoomSummary[]>("/api/v1/rooms", {
    cache: "no-store",
  });
}

export async function joinRoom(roomId: string): Promise<JoinRoomResult> {
  if (shouldUseMocks()) {
    const room = MOCK_ROOMS.find((candidate) => candidate.id === roomId);
    if (!room) {
      throw new ApiRequestError(
        "This room does not exist or has been closed.",
        404,
        "ROOM_NOT_FOUND",
      );
    }
    const { id, name, description } = room;
    return { room: { id, name, description }, nickname: "Quiet Otter" };
  }

  return apiFetch<JoinRoomResult>(`/api/v1/rooms/${roomId}/join`, {
    method: "POST",
    auth: true,
  });
}

export async function heartbeatRoom(roomId: string): Promise<void> {
  if (shouldUseMocks()) return;

  await apiFetch(`/api/v1/rooms/${roomId}/heartbeat`, {
    method: "POST",
    auth: true,
  });
}

export async function sendRoomMessage(
  roomId: string,
  body: string,
  nickname: string,
): Promise<ChatMessage> {
  if (shouldUseMocks()) {
    return {
      id: `demo-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      room_id: roomId,
      nickname,
      body,
      created_at: new Date().toISOString(),
    };
  }

  return apiFetch<ChatMessage>(`/api/v1/rooms/${roomId}/messages`, {
    method: "POST",
    body: JSON.stringify({ body }),
    auth: true,
  });
}
