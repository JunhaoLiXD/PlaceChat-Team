-- Realtime authorization (PlaceChat Technical Design §6.5).
--
-- Signed-in browsers, including anonymous students, may receive Broadcast messages on the
-- "rooms" channel and on every "room:{room_id}" channel. There is no insert policy, so browsers
-- can never send; only FastAPI publishes, through the Realtime REST endpoint with the secret key.
--
-- Never put "alter table realtime.messages enable row level security" in a migration:
-- RLS is already on, and the statement fails and aborts the migration.

create policy "signed-in users receive PlaceChat broadcasts"
on realtime.messages for select to authenticated
using (
  realtime.messages.extension = 'broadcast'
  and ((select realtime.topic()) = 'rooms'
       or (select realtime.topic()) like 'room:%')
);
