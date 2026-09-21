import asyncio
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, GetChannelRecommendationsRequest
from app.validator.contact_extractor import extract_contacts

async def inspect(ch_name):
    client = TelegramClient('/app/sessions/spiderweb_session', 39064636, '72d90d8ac46e9293e3d5254d9645e4f9')
    await client.connect()
    try:
        entity = await client.get_entity(ch_name)
        print("Type:", type(entity).__name__)
        print("Title:", getattr(entity, 'title', None))
        print("Username:", getattr(entity, 'username', None))
        
        full = await client(GetFullChannelRequest(entity))
        full_chat = full.full_chat
        about = getattr(full_chat, 'about', '')
        pinned_id = getattr(full_chat, 'pinned_msg_id', None)
        print("Members:", getattr(full_chat, 'participants_count', 0))
        print("About:", about)
        print("Pinned Msg ID:", pinned_id)
        
        pinned_text = ""
        if pinned_id:
            msg = await client.get_messages(entity, ids=pinned_id)
            if msg and msg.message:
                pinned_text = msg.message
                print("Pinned Text:", pinned_text[:200])

        contacts = extract_contacts(text="", description=about, channel_username=ch_name, pinned_text=pinned_text)
        print("Extracted Contacts:", contacts)

        recs = await client(GetChannelRecommendationsRequest(channel=entity))
        print(f"Recommendations count: {len(recs.chats)}")
        for c in recs.chats[:5]:
            print("  Rec:", getattr(c, 'title', ''), "@" + getattr(c, 'username', 'no_user'))
            
    except Exception as e:
        print("Error:", e)
    finally:
        await client.disconnect()

if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else 'ABOSALEM2003'
    asyncio.run(inspect(target))
