import asyncio
import os
import sys
from telethon import TelegramClient

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("user_session NOT authorized!")
        await client.disconnect()
        return

    import telethon.tl.functions.messages as messages_fn
    import telethon.tl.functions.chatlists as chatlists_fn
    from telethon.tl.types import DialogFilter, TextWithEntities, InputChatlistDialogFilter

    print("Fetching active and archived dialogs...")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived error: {e}")

    all_dialogs = d_active + d_archived
    seen_ids = set()

    all_admin_channels = []
    can_share_channels = []
    cannot_share_channels = []

    for d in all_dialogs:
        if d.is_channel or d.is_group:
            cid = d.id
            if cid in seen_ids:
                continue
            ent = d.entity
            left = getattr(ent, 'left', False)
            kicked = getattr(ent, 'kicked', False)
            deactivated = getattr(ent, 'deactivated', False)
            creator = getattr(ent, 'creator', False)
            admin_rights = getattr(ent, 'admin_rights', None)
            is_chat_admin = getattr(ent, 'admin', False)

            if not left and not kicked and not deactivated:
                if creator or admin_rights is not None or is_chat_admin:
                    seen_ids.add(cid)
                    all_admin_channels.append(d)
                    
                    # Check if user has permission to share in chatlists (creator OR admin_rights.invite_users)
                    can_invite = creator or (admin_rights and getattr(admin_rights, 'invite_users', False))
                    if can_invite:
                        can_share_channels.append(d)
                    else:
                        cannot_share_channels.append(d)

    print(f"\n--- TELEGRAM PERMISSIONS ANALYSIS ---")
    print(f"Total Admin Channels/Groups: {len(all_admin_channels)}")
    print(f"Channels where @tamerads1 HAS Share/Invite Permission: {len(can_share_channels)}")
    print(f"Channels where @tamerads1 LACKS Share/Invite Permission: {len(cannot_share_channels)}")

    print(f"\n--- TEST EXPORT CHATLIST INVITE API ---")
    admin_peers_all = [d.input_entity for d in all_admin_channels]
    
    # Create fresh DialogFilter ID 122
    filter_122 = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
        include_peers=admin_peers_all,
        exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=filter_122))
    print(f"✓ Created fresh 'My_Channels' Folder (ID 122) on Telegram with ALL {len(admin_peers_all)} input peers.")

    # Export Chatlist Invite
    try:
        folder_input = InputChatlistDialogFilter(filter_id=122)
        invite_res = await client(chatlists_fn.ExportChatlistInviteRequest(
            chatlist=folder_input,
            title="My_Channels",
            peers=admin_peers_all
        ))
        invite_obj = invite_res.invite
        already_peers = getattr(invite_res, 'chats', [])
        print(f"\n✓ Exported Link: {getattr(invite_obj, 'url', 'N/A')}")
        print(f"✓ Telegram Server Returned Peers Count in Link: {len(already_peers)}")
    except Exception as ex:
        print(f"Export Chatlist Error: {ex}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
