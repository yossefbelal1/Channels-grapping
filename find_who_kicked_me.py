"""
Find which channels the user was removed from and who removed them.
"""
import asyncio
import sys
import os
from datetime import datetime, timezone
from telethon import TelegramClient
from telethon.tl.functions.channels import GetAdminLogRequest, GetChannelsRequest
from telethon.tl.types import (
    Channel, Chat,
    ChannelAdminLogEventActionParticipantToggleBan,
    ChannelAdminLogEventActionParticipantToggleAdmin,
    ChannelAdminLogEventActionParticipantLeave,
    ChannelAdminLogEventsFilter
)

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT authorized!")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (ID={me.id}) | Premium: {me.premium}")

    print("\n=== STEP 1: SCANNING ALL CURRENT DIALOGS ===")
    current_admin = {}    # id -> (title, entity, input_entity)
    current_kicked = []   # (id, title) - kicked channels still in dialog list

    async for dialog in client.iter_dialogs(limit=None):
        ent = dialog.entity
        if not isinstance(ent, (Channel, Chat)):
            continue
        title = getattr(ent, 'title', str(ent.id))

        # Explicitly kicked
        if getattr(ent, 'kicked', False):
            current_kicked.append((ent.id, title, dialog.input_entity))
            continue

        if getattr(ent, 'left', False) or getattr(ent, 'deactivated', False):
            continue

        is_admin = (getattr(ent, 'creator', False) or
                    getattr(ent, 'admin_rights', None) is not None or
                    getattr(ent, 'admin', False))
        if is_admin:
            current_admin[ent.id] = (title, ent, dialog.input_entity)

    # Also scan archived
    async for dialog in client.iter_dialogs(limit=None, folder=1):
        ent = dialog.entity
        if not isinstance(ent, (Channel, Chat)):
            continue
        title = getattr(ent, 'title', str(ent.id))
        if getattr(ent, 'kicked', False):
            if not any(k[0] == ent.id for k in current_kicked):
                current_kicked.append((ent.id, title, dialog.input_entity))
            continue
        if getattr(ent, 'left', False) or getattr(ent, 'deactivated', False):
            continue
        is_admin = (getattr(ent, 'creator', False) or
                    getattr(ent, 'admin_rights', None) is not None or
                    getattr(ent, 'admin', False))
        if is_admin and ent.id not in current_admin:
            current_admin[ent.id] = (title, ent, dialog.input_entity)

    print(f"Currently ADMIN in: {len(current_admin)} channels/groups")
    print(f"Kicked channels in dialog list: {len(current_kicked)}")

    if current_kicked:
        print("\n🚫 CHANNELS YOU WERE KICKED FROM (found in dialogs):")
        for cid, title, _ in current_kicked:
            print(f"  ❌ {title} (ID={cid})")

    print("\n=== STEP 2: CHECK ADMIN LOGS FOR KICK/DEMOTE EVENTS ===")
    suspicious_events = []

    for cid, (title, ent, ip) in list(current_admin.items()):
        if not isinstance(ent, Channel):
            continue
        try:
            log_filter = ChannelAdminLogEventsFilter(
                join=False, leave=False, invite=False,
                ban=True, unban=False, kick=True, unkick=False,
                promote=False, demote=True,
                info=False, settings=False, pinned=False,
                edit=False, delete=False, group_call=False,
                invites=False, send=False
            )
            result = await client(GetAdminLogRequest(
                channel=ip, q='',
                filter=log_filter, admins=[],
                max_id=0, min_id=0, limit=20
            ))
            for event in result.events:
                action = event.action
                actor_id = event.user_id
                date_str = datetime.fromtimestamp(event.date, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')

                # Check ToggleBan (kick/ban)
                if isinstance(action, ChannelAdminLogEventActionParticipantToggleBan):
                    new_part = action.new_participant
                    old_part = action.prev_participant
                    target_uid = getattr(new_part, 'peer', None)
                    if target_uid:
                        target_uid = getattr(target_uid, 'user_id', None)
                    if not target_uid:
                        target_uid = getattr(old_part, 'peer', None)
                        if target_uid:
                            target_uid = getattr(target_uid, 'user_id', None)

                    if target_uid == me.id:
                        banned_rights = getattr(new_part, 'banned_rights', None)
                        if banned_rights and getattr(banned_rights, 'view_messages', False):
                            action_label = 'KICKED YOU'
                        else:
                            action_label = 'BANNED/RESTRICTED YOU'
                        suspicious_events.append({
                            'channel': title, 'action': action_label,
                            'actor_id': actor_id, 'date': date_str
                        })

                # Check ToggleAdmin (demote)
                elif isinstance(action, ChannelAdminLogEventActionParticipantToggleAdmin):
                    prev = action.prev_participant
                    new = action.new_participant
                    prev_uid = getattr(prev, 'user_id', None)
                    new_uid = getattr(new, 'user_id', None)
                    uid = prev_uid or new_uid
                    if uid == me.id:
                        prev_rights = getattr(prev, 'admin_rights', None)
                        new_rights = getattr(new, 'admin_rights', None)
                        if prev_rights and not new_rights:
                            suspicious_events.append({
                                'channel': title, 'action': 'DEMOTED YOU (removed admin)',
                                'actor_id': actor_id, 'date': date_str
                            })

        except Exception as e:
            pass  # No access or not a supergroup

    # Resolve actor names
    print(f"\n=== RESULTS: WHO KICKED/DEMOTED YOU ===\n")
    if suspicious_events:
        for ev in suspicious_events:
            try:
                actor = await client.get_entity(ev['actor_id'])
                actor_name = f"{getattr(actor, 'first_name', '')} {getattr(actor, 'last_name', '')}".strip()
                actor_username = f"@{actor.username}" if getattr(actor, 'username', None) else f"(ID={ev['actor_id']})"
            except Exception:
                actor_name = "Unknown"
                actor_username = f"(ID={ev['actor_id']})"
            print(f"📢 Channel : {ev['channel']}")
            print(f"   Action  : {ev['action']}")
            print(f"   By      : {actor_name} {actor_username}")
            print(f"   When    : {ev['date']} UTC")
            print()
    else:
        print("No kick/demote events found in accessible admin logs.")

    print(f"\n=== FINAL SUMMARY ===")
    print(f"Current admin channels : {len(current_admin)}")
    print(f"Kicked (in dialog list): {len(current_kicked)}")
    if current_kicked:
        print("\nFull kicked channels list:")
        for cid, title, _ in current_kicked:
            print(f"  ❌ {title} (ID={cid})")

    # Restart workers
    await client.disconnect()
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
