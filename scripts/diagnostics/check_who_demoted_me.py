"""
Check admin log for specific channels where user lost admin rights.
Finds who demoted them.
"""
import asyncio
import sys
import os
from datetime import datetime, timezone
from telethon import TelegramClient
from telethon.tl.functions.channels import GetAdminLogRequest
from telethon.tl.types import (
    Channel,
    ChannelAdminLogEventActionParticipantToggleAdmin,
    ChannelAdminLogEventActionParticipantToggleBan,
    ChannelAdminLogEventsFilter
)

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

# Channels where user lost admin (from comparison)
TARGET_CHANNELS = [
    (3556765779, "الأسطورة للتداول"),
    (3964939153, "BLACK HORSE ACADEMY"),
    (3935334777, "MICHAEL FX TRADER / GOLD PLATINUM TRADER"),
]

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT authorized!")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (ID={me.id})")
    print(f"Looking for who removed your admin rights...\n")

    for cid, name in TARGET_CHANNELS:
        print(f"{'='*50}")
        print(f"📢 Channel: {name} (ID={cid})")
        try:
            entity = await client.get_entity(cid)
            ip = await client.get_input_entity(entity)

            # Check ALL recent admin log events (no filter to catch everything)
            result = await client(GetAdminLogRequest(
                channel=ip,
                q='',
                admins=[],
                max_id=0,
                min_id=0,
                limit=50
            ))

            found = False
            for event in result.events:
                action = event.action
                actor_id = event.user_id
                date_str = datetime.fromtimestamp(event.date, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

                # Demote event
                if isinstance(action, ChannelAdminLogEventActionParticipantToggleAdmin):
                    prev = action.prev_participant
                    new = action.new_participant
                    prev_uid = getattr(prev, 'user_id', None)
                    new_uid = getattr(new, 'user_id', None)
                    uid = prev_uid or new_uid

                    if uid == me.id:
                        prev_rights = getattr(prev, 'admin_rights', None)
                        new_rights = getattr(new, 'admin_rights', None)
                        action_label = "DEMOTED (removed admin)" if (prev_rights and not new_rights) else "Admin rights changed"
                        try:
                            actor = await client.get_entity(actor_id)
                            actor_name = f"{getattr(actor, 'first_name', '')} {getattr(actor, 'last_name', '')}".strip()
                            actor_uname = f"@{actor.username}" if getattr(actor, 'username', None) else f"ID={actor_id}"
                        except Exception:
                            actor_name, actor_uname = "Unknown", f"ID={actor_id}"
                        print(f"  🔴 Action : {action_label}")
                        print(f"  👤 By     : {actor_name} ({actor_uname})")
                        print(f"  🕐 When   : {date_str}")
                        found = True

                # Ban/kick event
                elif isinstance(action, ChannelAdminLogEventActionParticipantToggleBan):
                    new_part = action.new_participant
                    peer = getattr(new_part, 'peer', None)
                    uid = getattr(peer, 'user_id', None) if peer else None
                    if uid == me.id:
                        try:
                            actor = await client.get_entity(actor_id)
                            actor_name = f"{getattr(actor, 'first_name', '')} {getattr(actor, 'last_name', '')}".strip()
                            actor_uname = f"@{actor.username}" if getattr(actor, 'username', None) else f"ID={actor_id}"
                        except Exception:
                            actor_name, actor_uname = "Unknown", f"ID={actor_id}"
                        banned_rights = getattr(new_part, 'banned_rights', None)
                        view_msgs = getattr(banned_rights, 'view_messages', False) if banned_rights else False
                        action_label = "KICKED/BANNED" if view_msgs else "Restricted"
                        print(f"  🔴 Action : {action_label}")
                        print(f"  👤 By     : {actor_name} ({actor_uname})")
                        print(f"  🕐 When   : {date_str}")
                        found = True

            if not found:
                print("  ℹ️  No demote/kick events found for you in last 50 admin log entries.")
                print("     (Either it happened before the log window, or you don't have log access)")

        except Exception as e:
            print(f"  ❌ Cannot access channel: {e}")
        print()

    await client.disconnect()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
