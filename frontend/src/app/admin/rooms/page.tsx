import type { Metadata } from "next";

import { AdminRoomManager } from "@/components/admin-room-manager";

export const metadata: Metadata = {
  title: "Rooms",
};

export default function AdminRoomsPage() {
  return <AdminRoomManager />;
}
