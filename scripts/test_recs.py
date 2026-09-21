import asyncio
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, GetChannelRecommendationsRequest

async def main():
    client = TelegramClient('/app/sessions/acc_12723433281', 39064636, '72d90d8ac46e9293e3d5254d9645e4f9')
    await client.connect()
    me = await client.get_me()
    print('Connected as:', me.first_name, me.username, me.phone)
    entity = await client.get_entity('almaalforex')
    print('Resolved almaalforex:', entity.title)
    
    full = await client(GetFullChannelRequest(channel=entity))
    full_chat = getattr(full, 'full_chat', None)
    pinned_id = getattr(full_chat, 'pinned_msg_id', None)
    print('Pinned msg id:', pinned_id)
    if pinned_id:
        msg = await client.get_messages(entity, ids=pinned_id)
        if msg:
            print('Pinned message text snippet:', (msg.message or '')[:100])

    recs = await client(GetChannelRecommendationsRequest(channel=entity))
    print('Similar channels found:', len(recs.chats))
    for c in recs.chats[:10]:
        print(' -', c.title, '@' + getattr(c, 'username', 'no_user'), f'({getattr(c, "participants_count", 0)} members)')
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
