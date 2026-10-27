import { Suspense } from "react";

import { RoomScreen } from "@/components/room-screen";

async function RoomContent({
  params,
}: {
  params: Promise<{ roomId: string }>;
}) {
  const { roomId } = await params;
  return <RoomScreen roomId={roomId} />;
}

export default function RoomPage({
  params,
}: {
  params: Promise<{ roomId: string }>;
}) {
  return (
    <Suspense>
      <RoomContent params={params} />
    </Suspense>
  );
}
