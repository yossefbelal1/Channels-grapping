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

    import telethon.tl.functions.chatlists as chatlists_fn
    import telethon.tl.functions.messages as messages_fn
    from telethon.tl.types import InputChatlistDialogFilter

    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    my_channels_filter = None
    for f in filters:
        title = ""
        if hasattr(f, 'title') and f.title:
            title = f.title.text if hasattr(f.title, 'text') else str(f.title)
        if title == "My_Channels":
            my_channels_filter = f

    if my_channels_filter:
        folder_input = InputChatlistDialogFilter(filter_id=my_channels_filter.id)
        exp_res = await client(chatlists_fn.GetExportedInvitesRequest(chatlist=folder_input))
        print("Exported invites raw object:")
        for inv in exp_res.invites:
            print("INVITE DIR:", [a for a in dir(inv) if not a.startswith('_')])
            print(f"URL: {getattr(inv, 'url', None)}")
            print(f"Title: {getattr(inv, 'title', None)}")
            print(f"Peers: {len(getattr(inv, 'peers', []))}")
            if hasattr(inv, 'url') and inv.url:
                # Test EditExportedInviteRequest
                try:
                    # In Telethon: EditExportedInviteRequest(chatlist=..., slug=..., title=..., peers=...)
                    # Extract slug from URL (t.me/addlist/SLUG)
                    slug = inv.url.split('/')[-1]
                    print(f"Extracted Slug: {slug}")
                    edit_res = await client(chatlists_fn.EditExportedInviteRequest(
                        chatlist=folder_input,
                        slug=slug,
                        peers=my_channels_filter.include_peers
                    ))
                    print("EditExportedInviteRequest SUCCESS:", edit_res)
                except Exception as edit_err:
                    print("EditExportedInviteRequest ERR:", edit_err)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
