// API shapes come from the generated `api-types.ts` (Technical Design §7.1), so the
// backend's OpenAPI schema is the only source. Regenerate with `npm run api-types`.
import type { components } from "@/lib/api-types";

type Schemas = components["schemas"];

export type RoomSummary = Schemas["RoomResponse"];
export type RoomCategory = RoomSummary["category"];
export type AdminRoom = Schemas["AdminRoomResponse"];
export type AdminRoomCreate = Schemas["RoomCreate"];
export type AdminRoomUpdate = Schemas["RoomUpdate"];

/** `POST /rooms/{id}/join`. The page already has the room from the list; it uses the nickname. */
export type JoinRoomResult = Schemas["JoinRoomResponse"];

/** The POST response and the `message.created` broadcast. `is_mine` comes with history (C3). */
export type ChatMessage = Schemas["MessageResponse"] & { is_mine?: boolean };

/** The §7.2 error shape. Errors are not part of the OpenAPI schema. */
export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    retry_after?: number;
  };
}

/** PBI-33's pending-report view; replace with its generated schema when available. */
export interface AdminReport {
  id: string;
  reason: "harassment" | "spam" | "other" | null;
  created_at: string;
  message: {
    id: string;
    body: string;
    nickname: string;
    created_at: string;
  };
  room: {
    id: string;
    name: string;
  };
}
