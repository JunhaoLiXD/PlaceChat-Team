export type RoomCategory =
  "library" | "dining" | "student life" | "academic" | "recreation";

export interface RoomSummary {
  id: string;
  name: string;
  description: string;
  category: RoomCategory;
  latitude: number;
  longitude: number;
  participant_count: number;
}

/** `POST /rooms/{id}/join`. The page already has the room from the list, so only the nickname is used. */
export interface JoinRoomResult {
  nickname: string;
}

export interface ChatMessage {
  id: string;
  room_id: string;
  nickname: string;
  body: string;
  created_at: string;
  is_mine?: boolean;
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    retry_after?: number;
  };
}
