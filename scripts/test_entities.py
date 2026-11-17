import asyncio
from telethon import TelegramClient

async def check_entities():
    c = TelegramClient('/app/sessions/reclaim_worker_session', 39064636, '72d90d8ac46e9293e3d5254d9645e4f9')
    await c.connect()
    targets = [
        'FX_MANAGEMENT_ADMIN',
        'goldmindac', 'Sultana_Fx_1', 'SULTANA_1_FX', 'MBAgoldforex', 'Sultan1gold',
        'gorillatrading0', 'masrawystrategiess', 'CryptoArabs1chat',
        'mustafaabdulqawi', 'KING_1FUTUR1', 'forexomniadmin'
    ]
    for t in targets:
        try:
            ent = await c.get_entity(t)
            print(f"{t} -> {type(ent).__name__} (id={ent.id})")
        except Exception as e:
            print(f"{t} -> Error: {e}")
    await c.disconnect()

if __name__ == '__main__':
    asyncio.run(check_entities())
