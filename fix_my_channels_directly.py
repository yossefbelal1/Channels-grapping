import asyncio
import os
import logging
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
from telethon.tl.types import DialogFilter, InputPeerSelf
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "32950512"))
API_HASH = os.getenv("API_HASH", "23f5be247297fe7645193f6f782dad67")
SESSION = os.path.join("sessions", "user_session")

def is_channel_or_chat_peer(peer):
    classname = peer.__class__.__name__
    return "Channel" in classname or "Chat" in classname

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("Client not authorized!")
        return

    # 1. Fetch all dialogs using iter_dialogs with pagination
    print("[*] Fetching all account dialogs via iter_dialogs...")
    all_dialogs = []
    async for d in client.iter_dialogs():
        all_dialogs.append(d)
    print(f"[+] Total dialogs fetched: {len(all_dialogs)}")

    # Build map of admin entities
    admin_peers_map = {}
    for d in all_dialogs:
        if not (d.is_channel or d.is_group):
            continue
        entity = d.entity
        left = getattr(entity, 'left', False)
        kicked = getattr(entity, 'kicked', False)
        deactivated = getattr(entity, 'deactivated', False)
        creator = getattr(entity, 'creator', False)
        admin_rights = getattr(entity, 'admin_rights', None)
        
        if not left and not kicked and not deactivated and (creator or admin_rights is not None):
            p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'id', None)
            if p_id:
                admin_peers_map[p_id] = (d.input_entity, d.name, getattr(entity, 'username', 'N/A'))

    print(f"[+] Total active admin channels/groups found across account: {len(admin_peers_map)}")

    # 2. Get all dialog filters (folders)
    res_filters = await client(GetDialogFiltersRequest())
    filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    TARGET_FOLDERS = {"My_Channels", "حملات", "No_Post", "Banned", "Only_Post"}

    for f in filters:
        if not hasattr(f, 'title'):
            continue
        title = f.title.text if hasattr(f.title, 'text') else str(f.title)
        
        if title in TARGET_FOLDERS:
            print(f"\n[*] Processing Folder: '{title}' (ID: {f.id}) | Current Peers: {len(f.include_peers)}")
            cleaned_peers = []
            changed = False

            if title == "My_Channels":
                # For My_Channels, ensure all active admin peers are included
                current_ids = set()
                for peer in f.include_peers:
                    p_id = getattr(peer, 'channel_id', None) or getattr(peer, 'chat_id', None) or getattr(peer, 'id', None)
                    # Verify if this peer is an active admin channel
                    is_admin_peer = False
                    if p_id in admin_peers_map:
                        is_admin_peer = True
                    else:
                        # Direct check via get_entity
                        try:
                            ent = await client.get_entity(peer)
                            if not getattr(ent, 'left', False) and not getattr(ent, 'kicked', False):
                                if getattr(ent, 'creator', False) or getattr(ent, 'admin_rights', None) is not None:
                                    is_admin_peer = True
                                    admin_peers_map[p_id] = (peer, getattr(ent, 'title', 'Channel'), getattr(ent, 'username', 'N/A'))
                        except Exception as e:
                            pass
                    
                    if is_admin_peer:
                        cleaned_peers.append(peer)
                        current_ids.add(p_id)
                    else:
                        changed = True
                        print(f"  [-] Removing non-admin peer id={p_id} from '{title}'")

                # Add missing admin channels
                for p_id, (input_peer, name, uname) in admin_peers_map.items():
                    if p_id not in current_ids:
                        cleaned_peers.append(input_peer)
                        changed = True
                        print(f"  [+] Adding missing admin channel '{name}' (@{uname}) to '{title}'")

            else:
                for peer in f.include_peers:
                    if is_channel_or_chat_peer(peer):
                        p_id = getattr(peer, 'channel_id', None) or getattr(peer, 'chat_id', None) or getattr(peer, 'id', None)
                        is_admin_peer = False
                        if p_id in admin_peers_map:
                            is_admin_peer = True
                        else:
                            try:
                                ent = await client.get_entity(peer)
                                if not getattr(ent, 'left', False) and not getattr(ent, 'kicked', False):
                                    if getattr(ent, 'creator', False) or getattr(ent, 'admin_rights', None) is not None:
                                        is_admin_peer = True
                            except Exception:
                                pass
                        
                        if is_admin_peer:
                            cleaned_peers.append(peer)
                        else:
                            changed = True
                            print(f"  [-] Removing non-admin peer id={p_id} from '{title}'")
                    else:
                        cleaned_peers.append(peer)

            if len(cleaned_peers) == 0:
                cleaned_peers = [InputPeerSelf()]
                changed = True

            if changed or len(cleaned_peers) != len(f.include_peers):
                print(f"[!] Updating folder '{title}' (ID: {f.id}) on Telegram server... (New count: {len(cleaned_peers)})")
                updated_filter = DialogFilter(
                    id=f.id,
                    title=f.title,
                    pinned_peers=f.pinned_peers if hasattr(f, 'pinned_peers') else [],
                    include_peers=cleaned_peers,
                    exclude_peers=f.exclude_peers if hasattr(f, 'exclude_peers') else [],
                    contacts=getattr(f, 'contacts', False),
                    non_contacts=getattr(f, 'non_contacts', False),
                    groups=getattr(f, 'groups', False),
                    broadcasts=getattr(f, 'broadcasts', False),
                    bots=getattr(f, 'bots', False),
                    exclude_muted=getattr(f, 'exclude_muted', False),
                    exclude_read=getattr(f, 'exclude_read', False),
                    exclude_archived=getattr(f, 'exclude_archived', False)
                )
                await client(UpdateDialogFilterRequest(id=f.id, filter=updated_filter))
                print(f"[+] Successfully updated folder '{title}' on Telegram server!")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
