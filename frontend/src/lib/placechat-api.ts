import { MOCK_ROOMS } from "@/lib/mock-data";
import { publicConfig, shouldUseMocks } from "@/lib/config";
import type {
  ApiErrorBody,
  ChatMessage,
  JoinRoomResult,
  RoomSummary,
} from "@/lib/placechat-types";

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${publicConfig.apiBaseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
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
    );
  }

  return (await response.json()) as T;
}

export async function listRooms(): Promise<RoomSummary[]> {
  // PBI-04 owns this endpoint. Local development can opt into deterministic rooms
  // until it lands, but configured deployments must surface real API failures.
  if (shouldUseMocks()) {
    return MOCK_ROOMS;
  }

  return apiFetch<RoomSummary[]>("/api/v1/rooms", {
    cache: "no-store",
  });
}

export async function joinRoom(
  room: RoomSummary,
  accessToken?: string,
): Promise<JoinRoomResult> {
  if (!accessToken) {
    return { room, nickname: "Quiet Otter" };
  }

  return apiFetch<JoinRoomResult>(`/api/v1/rooms/${room.id}/join`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export async function heartbeatRoom(roomId: string, accessToken?: string) {
  if (!accessToken) return;

  await apiFetch(`/api/v1/rooms/${roomId}/heartbeat`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export async function sendRoomMessage(
  roomId: string,
  body: string,
  nickname: string,
  accessToken?: string,
): Promise<ChatMessage> {
  if (!accessToken) {
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
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
