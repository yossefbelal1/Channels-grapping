import asyncio
from telethon import TelegramClient

async def check(target):
    c = TelegramClient('/app/sessions/spiderweb_session', 39064636, '72d90d8ac46e9293e3d5254d9645e4f9')
    await c.connect()
    ent = await c.get_entity(target)
    msgs = await c.get_messages(ent, limit=200)
    print(f"--- Checking {len(msgs)} posts in @{target} ---")
    for m in msgs:
        if m.message and ('@' in m.message or 'تواصل' in m.message or 'خاص' in m.message or 'دعم' in m.message or 'اشتراك' in m.message):
            print(f"\n--- Msg {m.id} ---")
            print(m.message)
    await c.disconnect()

if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else 'haiderfx'
    asyncio.run(check(target))
