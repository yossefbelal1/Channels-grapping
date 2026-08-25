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
    from telethon.tl.types import InputChatlistDialogFilter

    print("Fetching active dialogs...")
    dialogs_active = await client.get_dialogs(limit=None)
    print("Fetching archived dialogs...")
    dialogs_archived = []
    try:
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived fetch note: {e}")

    all_dialogs = dialogs_active + dialogs_archived
    channels = [d for d in all_dialogs if d.is_channel or d.is_group]
    print(f"\nTotal channels & groups in dialogs: {len(channels)}")

    # Fetch My_Channels filter include_peers
    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    all_filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    my_filter = None
    for f in all_filters:
        if hasattr(f, 'title') and f.title:
            t = f.title.text if hasattr(f.title, 'text') else str(f.title)
            if t == "My_Channels":
                my_filter = f
                break

    my_channel_peer_ids = set()
    if my_filter:
        for p in getattr(my_filter, 'include_peers', []):
            pid = getattr(p, 'channel_id', None) or getattr(p, 'chat_id', None) or getattr(p, 'id', None)
            if pid:
                my_channel_peer_ids.add(pid)

    print(f"\nCurrent 'My_Channels' folder peer count: {len(my_channel_peer_ids)}")

    # Detailed inspection of ALL channels/groups
    detected_admins = []
    potential_admins = []
    other_channels = []

    for d in channels:
        ent = d.entity
        name = d.name
        username = getattr(ent, 'username', 'N/A')
        p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'user_id', None) or getattr(d.input_entity, 'id', None)
        left = getattr(ent, 'left', False)
        kicked = getattr(ent, 'kicked', False)
        deactivated = getattr(ent, 'deactivated', False)
        creator = getattr(ent, 'creator', False)
        admin_rights = getattr(ent, 'admin_rights', None)

        is_in_my_folder = p_id in my_channel_peer_ids

        info_str = f"'{name}' (@{username}) [id={p_id}] | creator={creator} | admin_rights={admin_rights} | left={left} | in_folder={is_in_my_folder}"

        if not left and not kicked and not deactivated:
            if creator or admin_rights is not None:
                detected_admins.append(info_str)
            else:
                # Let's check if user is admin in Chat (small group) or has admin permissions
                if getattr(ent, 'admin', False):
                    potential_admins.append(f"[CHAT_ADMIN] {info_str}")
                else:
                    other_channels.append(info_str)

    print(f"\n--- DETECTED ADMIN CHANNELS ({len(detected_admins)}) ---")
    for item in detected_admins:
        print(f"  ✓ {item}")

    print(f"\n--- POTENTIAL / CHAT ADMIN CHANNELS ({len(potential_admins)}) ---")
    for item in potential_admins:
        print(f"  ? {item}")

    # ALSO: Fetch exported chatlist share links for My_Channels
    if my_filter:
        folder_input = InputChatlistDialogFilter(filter_id=my_filter.id)
        exp_res = await client(chatlists_fn.GetExportedInvitesRequest(chatlist=folder_input))
        invites = getattr(exp_res, 'invites', [])
        for inv in invites:
            print(f"\n--- SHARE LINK DETAILED SUMMARY ---")
            print(f"URL: {inv.url}")
            print(f"Share Link Peers Count: {len(inv.peers)}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
