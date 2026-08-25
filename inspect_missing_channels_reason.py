import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, UsernameInvalidError, UsernameNotOccupiedError, ChannelInvalidError, ChatAdminRequiredError

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

TEST_MISSING = [
    ("AlMANSORI 📊", "Almansori_11", -1002047969365),
    ("KING FX💯🔥", "KING2024FX", -1001789800455),
    ("🔥 Dr ALi FOREX 🔥", "dr_ali_forex", -1002335367368),
    ("سيادة💎 الذهب🥇GOLD", "sssesssessse", -1003954807820),
    ("SNIPER GOLD", "Lady_ALGold", -1001531870553),
    ("الأسطورة للتداول", "Legend_2_Trading", -1003556765779),
    ("ARAB ICT 🔐", "arabictchannel", -1001222348201),
    ("ادارة حسابات تداول الفوركس", "adarhh", -1003115432387),
    ("Smart Liquidity", "LOCAL_FX1", -1003162275358),
    ("محمد المطيري تداول", "MohammedAlMutairi11", -1003745828370)
]

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("user_session NOT authorized!")
        await client.disconnect()
        return

    print("Checking status of missing channels directly on Telegram...\n")
    for name, uname, cid in TEST_MISSING:
        target = f"@{uname}" if uname else cid
        try:
            ent = await client.get_entity(target)
            left = getattr(ent, 'left', False)
            kicked = getattr(ent, 'kicked', False)
            admin = getattr(ent, 'admin', False) or getattr(ent, 'creator', False) or getattr(ent, 'admin_rights', None) is not None
            print(f"★ Channel: '{name}' ({target}) -> EXITS on Telegram. left={left}, kicked={kicked}, isAdmin={admin}")
        except ChannelPrivateError:
            print(f"🔒 Channel: '{name}' ({target}) -> Channel is PRIVATE / User was REMOVED/KICKED from channel.")
        except (UsernameInvalidError, UsernameNotOccupiedError, ChannelInvalidError):
            print(f"🚫 Channel: '{name}' ({target}) -> BANNED / DELETED / Username Changed by Telegram.")
        except Exception as e:
            print(f"⚠️ Channel: '{name}' ({target}) -> Error: {e}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
